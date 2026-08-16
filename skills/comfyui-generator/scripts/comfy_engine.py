import os
import json
import glob
import urllib.request
import urllib.parse
import uuid
import time
import random
import argparse
import mimetypes
import struct

try:
    from PIL import Image as PILImage
except Exception:
    PILImage = None

DEFAULT_COMFY_HOST = "127.0.0.1:8000"
DEFAULT_COMFY_SCHEME = "http"
DEFAULT_USERDATA_DIR = "workflows"
WORKFLOW_DIRS = [
    r"C:\lumichy\ComfyUI\user\default\workflows",
    r"C:\Users\lumic\Downloads"
]


# ---------------------------------------------------------------------------
# Server configuration (ComfyUI may run on a remote / different host)
# ---------------------------------------------------------------------------
def get_comfy_host():
    return os.environ.get("COMFYUI_HOST", DEFAULT_COMFY_HOST)

def get_comfy_scheme():
    return os.environ.get("COMFYUI_SCHEME", DEFAULT_COMFY_SCHEME)

def get_comfy_base_url():
    return f"{get_comfy_scheme()}://{get_comfy_host()}"

def get_comfy_headers():
    """Optional auth headers (e.g. for servers started with --auth)."""
    headers = {}
    token = os.environ.get("COMFYUI_API_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


# ---------------------------------------------------------------------------
# Resolution helpers (match output size to a reference image)
# ---------------------------------------------------------------------------
def get_image_size(path):
    """Return (width, height) of an image using PIL when available, otherwise
    fall back to lightweight header parsing (PNG / JPEG / WebP)."""
    if PILImage is not None:
        try:
            with PILImage.open(path) as im:
                return im.size
        except Exception:
            pass
    try:
        with open(path, "rb") as f:
            head = f.read(64)
    except Exception:
        return None
    if head[:8] == b"\x89PNG\r\n\x1a\n" and len(head) >= 24:
        return struct.unpack(">II", head[16:24])
    if head[:3] == b"\xff\xd8\xff":  # JPEG
        with open(path, "rb") as f:
            f.seek(2)
            while True:
                b = f.read(1)
                if not b:
                    break
                if b != b"\xff":
                    continue
                marker = f.read(1)
                if marker in (b"\xc0", b"\xc1", b"\xc2", b"\xc3", b"\xc5", b"\xc6", b"\xc7",
                              b"\xc9", b"\xca", b"\xcb", b"\xcd", b"\xce", b"\xcf"):
                    seg = f.read(3)
                    return (struct.unpack(">HH", seg[1:])[1], struct.unpack(">HH", seg[1:])[0])
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":  # WebP
        return (struct.unpack("<I", head[26:30])[0] & 0x3FFF,
                struct.unpack("<I", head[30:34])[0] & 0x3FFF)
    return None


def compute_resolution_from_image(img_w, img_h, max_short=768, max_long=1344, multiple=32):
    """Compute an output resolution that preserves the reference image's
    aspect ratio while staying inside the model's canvas (short edge ~768,
    long edge capped, snapped to a multiple of 32). Returns (None, None) on
    invalid input."""
    if not img_w or not img_h:
        return None, None
    aspect = img_w / img_h
    if aspect >= 1.0:  # landscape: height is the short edge
        h = max_short
        w = round(max_short * aspect)
    else:              # portrait: width is the short edge
        w = max_short
        h = round(max_short / aspect)
    if max(w, h) > max_long:  # clamp the long edge, preserving aspect ratio
        scale = max_long / max(w, h)
        w, h = round(w * scale), round(h * scale)
    w = max(multiple, round(w / multiple) * multiple)
    h = max(multiple, round(h / multiple) * multiple)
    return w, h

def server_reachable(timeout=5):
    """Return True if the configured ComfyUI server responds to /system_stats."""
    try:
        req = urllib.request.Request(f"{get_comfy_base_url()}/system_stats", headers=get_comfy_headers())
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def upload_image(image_path):
    """Upload input image to ComfyUI server via /upload/image API."""
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Input image not found: {image_path}")

    filename = os.path.basename(image_path)
    mime_type, _ = mimetypes.guess_type(image_path)
    if not mime_type:
        mime_type = "image/png"

    with open(image_path, "rb") as f:
        file_bytes = f.read()

    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
    body = []

    body.append(f"--{boundary}".encode())
    body.append(f'Content-Disposition: form-data; name="image"; filename="{filename}"'.encode())
    body.append(f"Content-Type: {mime_type}".encode())
    body.append(b"")
    body.append(file_bytes)

    body.append(f"--{boundary}".encode())
    body.append(b'Content-Disposition: form-data; name="overwrite"')
    body.append(b"")
    body.append(b"true")

    body.append(f"--{boundary}--".encode())
    body.append(b"")

    payload = b"\r\n".join(body)
    headers = get_comfy_headers()
    headers['Content-Type'] = f'multipart/form-data; boundary={boundary}'

    req = urllib.request.Request(f"{get_comfy_base_url()}/upload/image", data=payload, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        res = json.loads(resp.read())
        uploaded_name = res.get("name", filename)
        print(f"Uploaded input image '{image_path}' -> ComfyUI as '{uploaded_name}'")
        return uploaded_name


# ---------------------------------------------------------------------------
# Remote (server-side) workflow discovery via the /api/userdata endpoints
# ---------------------------------------------------------------------------
def list_server_workflows(timeout=15):
    """List workflows stored on the ComfyUI server.

    Returns a list of server-relative paths (e.g. 'text2image_qwen.json').
    """
    userdata_dir = os.environ.get("COMFYUI_USERDATA_DIR", DEFAULT_USERDATA_DIR)
    query = urllib.parse.urlencode({
        "dir": userdata_dir,
        "recurse": "true",
        "split": "false",
        "full_info": "true",
    })
    url = f"{get_comfy_base_url()}/api/userdata?{query}"
    req = urllib.request.Request(url, headers=get_comfy_headers())
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())

    # The listing returns paths relative to `dir`, so prefix them to get paths
    # relative to the user root (needed to fetch each file afterwards).
    paths = []
    for item in data:
        if isinstance(item, dict):
            path = item.get("path") or item.get("name")
        else:
            path = item
        if not path or not str(path).lower().endswith(".json"):
            continue
        paths.append(f"{userdata_dir.rstrip('/')}/{str(path)}")
    return paths

def fetch_server_workflow(rel_path, timeout=30):
    """Download a workflow JSON from the ComfyUI server by relative path."""
    encoded = urllib.parse.quote(rel_path, safe="")
    url = f"{get_comfy_base_url()}/api/userdata/{encoded}"
    req = urllib.request.Request(url, headers=get_comfy_headers())
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


# ---------------------------------------------------------------------------
# Workflow classification
# ---------------------------------------------------------------------------
def classify_workflow(filename, data=None):
    """Classify a workflow as 'image', 'video', or 'i2v'.

    Returns None for templates that should be skipped (e.g. frontend-only
    subgraph UUID templates with no runnable nodes even inside their bodies).
    """
    node_types = []
    if data is not None:
        if isinstance(data, dict):
            nodes = data.get("nodes", [])
        else:
            nodes = []
        if nodes:
            node_types = [n.get("type", "") for n in nodes if isinstance(n, dict)]
        elif isinstance(data, dict):
            node_types = [v.get("class_type", "") for k, v in data.items() if isinstance(v, dict)]

    # Subgraph templates keep their real nodes in definitions.subgraphs[*].nodes.
    subgraph_types = []
    if isinstance(data, dict):
        for sg in (data.get("definitions", {}) or {}).get("subgraphs", []) or []:
            for n in sg.get("nodes", []) or []:
                if isinstance(n, dict):
                    subgraph_types.append(n.get("type", ""))

    # Skip workflows that contain Subgraph UUIDs (UI frontend only) and expose
    # no runnable nodes even inside their subgraph bodies.
    if any(len(t) > 30 and "-" in t for t in node_types) and not subgraph_types:
        return None

    all_types = node_types + subgraph_types
    fn_lower = os.path.basename(filename).lower()
    is_i2v = ("i2v" in fn_lower or "image_to_video" in fn_lower or "image to video" in fn_lower
              or any("Image to Video" in t or "i2v" in t.lower() for t in all_types))

    is_video = is_i2v or any(
        t in ["VHS_VideoCombine", "SaveAnimatedWEBP", "AnimateDiffLoaderWithCheckpoints",
             "WanVideoSampler", "MiniMax H3 Text to Video", "MiniMax H3 Image to Video"]
        or "Video" in t or "video" in t or "Animate" in t
        for t in all_types
    )

    if is_i2v:
        return "i2v"
    if is_video:
        return "video"
    return "image"


# ---------------------------------------------------------------------------
# Workflow discovery (server + local fallback)
# ---------------------------------------------------------------------------
def scan_server_workflows():
    """Discover workflows stored on the (possibly remote) ComfyUI server."""
    workflows = []
    try:
        paths = list_server_workflows()
    except Exception as e:
        print(f"[warn] Cannot reach ComfyUI server at {get_comfy_base_url()}: {e}")
        return workflows

    for rel_path in paths:
        try:
            data = fetch_server_workflow(rel_path)
            media_type = classify_workflow(rel_path, data)
            if media_type is None:
                continue
            workflows.append({
                "name": os.path.basename(rel_path),
                "path": rel_path,
                "media_type": media_type,
                "source": "server",
            })
        except Exception:
            continue
    return workflows

def scan_local_workflows():
    """Discover workflows from local workflow directories (offline fallback)."""
    workflows = []
    for wdir in WORKFLOW_DIRS:
        if not os.path.exists(wdir):
            continue
        for filepath in glob.glob(os.path.join(wdir, "*.json")):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                media_type = classify_workflow(filepath, data)
                if media_type is None:
                    continue
                workflows.append({
                    "name": os.path.basename(filepath),
                    "path": filepath,
                    "media_type": media_type,
                    "source": "local",
                })
            except Exception:
                continue
    return workflows

def scan_workflows():
    """Merge server-side and local workflows (server entries take priority)."""
    merged = {}
    for wf in scan_server_workflows():
        merged[wf["name"]] = wf
    for wf in scan_local_workflows():
        merged.setdefault(wf["name"], wf)
    return list(merged.values())

def load_workflow_data(wf):
    """Load a workflow JSON, either from the server or from local disk."""
    if wf.get("source") == "server":
        return fetch_server_workflow(wf["path"])
    with open(wf["path"], 'r', encoding='utf-8') as f:
        return json.load(f)

def build_default_minimax_i2v_api(prompt_text, image_name, seed=None, width=768, height=768, duration_sec=5):
    """Build native API prompt for MiniMax H3 Image to Video."""
    frames = max(5, round((duration_sec or 5) * 24))
    snapped_length = frames + (5 - (frames % 17)) % 17
    rnd_seed = seed if seed is not None else random.randint(1, 1000000000)

    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "minimax_h3_fl2va_pruned_int8_convrot.safetensors", "weight_dtype": "default"}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "type": "minimax", "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_video_vae_fp16.safetensors"}},
        "5": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
        "6": {
            "class_type": "MiniMaxH3ImageToVideo",
            "inputs": {
                "clip": ["3", 0], "vae": ["4", 0], "first_frame": ["1", 0],
                "prompt": prompt_text or "a video",
                "width": width or 768, "height": height or 768, "length": snapped_length
            }
        },
        "7": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "8": {"class_type": "BasicScheduler", "inputs": {"model": ["2", 0], "scheduler": "simple", "steps": 20, "denoise": 1.0}},
        "9": {"class_type": "RandomNoise", "inputs": {"noise_seed": rnd_seed}},
        "10": {"class_type": "BasicGuider", "inputs": {"model": ["2", 0], "conditioning": ["6", 0]}},
        "11": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["9", 0], "guider": ["10", 0], "sampler": ["7", 0],
                "sigmas": ["8", 0], "latent_image": ["6", 1]
            }
        },
        "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["4", 0]}},
        "13": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["11", 0], "vae": ["5", 0]}},
        "14": {"class_type": "CreateVideo", "inputs": {"images": ["12", 0], "audio": ["13", 0], "fps": 24.0, "bit_depth": 8}},
        "15": {"class_type": "SaveVideo", "inputs": {"video": ["14", 0], "filename_prefix": "ComfyUI_Agent_video", "format": "auto", "codec": "auto"}}
    }

def build_default_minimax_t2v_api(prompt_text, seed=None, width=768, height=768, duration_sec=5):
    """Build native API prompt for MiniMax H3 Text to Video."""
    frames = max(5, round((duration_sec or 5) * 24))
    snapped_length = frames + (5 - (frames % 17)) % 17
    rnd_seed = seed if seed is not None else random.randint(1, 1000000000)

    return {
        "2": {"class_type": "UNETLoader", "inputs": {"unet_name": "minimax_h3_fl2va_pruned_int8_convrot.safetensors", "weight_dtype": "default"}},
        "3": {"class_type": "CLIPLoader", "inputs": {"clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", "type": "minimax", "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_video_vae_fp16.safetensors"}},
        "5": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
        "6": {
            "class_type": "MiniMaxH3ImageToVideo",
            "inputs": {
                "clip": ["3", 0], "vae": ["4", 0],
                "prompt": prompt_text or "a video",
                "width": width or 768, "height": height or 768, "length": snapped_length
            }
        },
        "7": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
        "8": {"class_type": "BasicScheduler", "inputs": {"model": ["2", 0], "scheduler": "simple", "steps": 20, "denoise": 1.0}},
        "9": {"class_type": "RandomNoise", "inputs": {"noise_seed": rnd_seed}},
        "10": {"class_type": "BasicGuider", "inputs": {"model": ["2", 0], "conditioning": ["6", 0]}},
        "11": {
            "class_type": "SamplerCustomAdvanced",
            "inputs": {
                "noise": ["9", 0], "guider": ["10", 0], "sampler": ["7", 0],
                "sigmas": ["8", 0], "latent_image": ["6", 1]
            }
        },
        "12": {"class_type": "VAEDecode", "inputs": {"samples": ["11", 0], "vae": ["4", 0]}},
        "13": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["11", 0], "vae": ["5", 0]}},
        "14": {"class_type": "CreateVideo", "inputs": {"images": ["12", 0], "audio": ["13", 0], "fps": 24.0, "bit_depth": 8}},
        "15": {"class_type": "SaveVideo", "inputs": {"video": ["14", 0], "filename_prefix": "ComfyUI_Agent_video", "format": "auto", "codec": "auto"}}
    }

CONTROL_AFTER_GENERATE_VALUES = {"fixed", "increment", "decrement", "randomize"}


def map_widget_values(inputs_def, widgets):
    """Map a node's widgets_values array onto its widget inputs.

    Returns {input_name: value}. Handles the 'control_after_generate' pseudo-
    values (e.g. 'fixed') that the UI inserts after seed-like widgets, and skips
    widget slots that are already driven by a linked input (their slot is null).
    """
    result = {}
    widget_inputs = [inp for inp in inputs_def if inp.get('widget') is not None]
    idx = 0
    for inp in widget_inputs:
        if idx >= len(widgets):
            break
        name = inp['name']
        value = widgets[idx]
        idx += 1
        if value is None:
            # Widget slot that has been converted to a socket (linked input).
            continue
        # Seed-like widgets carry a trailing control_after_generate string.
        if idx < len(widgets) and widgets[idx] in CONTROL_AFTER_GENERATE_VALUES:
            idx += 1
        result[name] = value
    return result


def flatten_subgraphs(ui_data, prompt_text=None, seed=None, width=None, height=None, duration=None):
    """Expand UI subgraph-instance templates into a flat node/link structure.

    Subgraph templates keep their real nodes inside
    ui_data["definitions"]["subgraphs"], while the top-level "nodes" list only
    contains placeholder instance nodes (UUID types). The server /prompt API
    only understands a flat graph, so each instance is replaced by its body:

      - body node ids are remapped to fresh ids to avoid collisions,
      - the instance's widget values / external links are injected into the
        exposed body inputs (returned as ``overrides`` for last-pass
        application by convert_ui_to_api_prompt),
      - the instance's output links are rewired to the body's output node.

    Returns (flat_ui, overrides) where flat_ui is {"nodes": [...], "links":
    [...]} in UI canvas format. Returns the input unchanged when no subgraph
    instances are present.
    """
    subgraphs = {
        sg.get("id"): sg
        for sg in (ui_data.get("definitions", {}) or {}).get("subgraphs", []) or []
        if sg.get("id")
    }
    if not subgraphs or not any(n.get("type", "") in subgraphs for n in ui_data.get("nodes", [])):
        return ui_data, {}

    nodes = list(ui_data.get("nodes", []))
    links = [list(l) for l in ui_data.get("links", [])]

    top_ids = [n["id"] for n in nodes if "id" in n]
    top_link_ids = [l[0] for l in links if l]
    next_node_id = (max(top_ids) + 1) if top_ids else 1
    next_link_id = (max(top_link_ids) + 1) if top_link_ids else 1

    new_nodes = []
    final_links = []
    overrides = {}
    removed_targets = set()
    link_rewrite = {}

    for node in nodes:
        ntype = node.get("type", "")
        if ntype not in subgraphs:
            new_nodes.append(node)
            continue

        sg = subgraphs[ntype]
        removed_targets.add(node["id"])

        body_nodes = {bn["id"]: bn for bn in sg.get("nodes", []) if "id" in bn}
        body_links = {bl.get("id"): bl for bl in sg.get("links", [])}

        # Fresh ids for the body nodes.
        idmap = {}
        for bn_id in body_nodes:
            idmap[bn_id] = next_node_id
            next_node_id += 1

        # Map original body link ids to the new ones assigned below.
        link_idmap = {}
        for bl in sg.get("links", []):
            if bl.get("id") is not None:
                link_idmap[bl["id"]] = next_link_id
                next_link_id += 1

        # Exposed inputs whose underlying body target is a widget input. The
        # instance node's widgets_values align to these in order.
        widgetable = []
        for ex in sg.get("inputs", []):
            lid = (ex.get("linkIds") or [None])[0]
            bl = body_links.get(lid)
            if not bl or bl.get("origin_id") != -10:
                continue
            tnode = body_nodes.get(bl.get("target_id"))
            tslot = bl.get("target_slot")
            if tnode and 0 <= tslot < len(tnode.get("inputs", [])) and \
               tnode["inputs"][tslot].get("widget") is not None:
                widgetable.append(ex.get("name"))
        widget_pos = {name: i for i, name in enumerate(widgetable)}

        inst_inputs = {i.get("name"): i for i in node.get("inputs", []) if i.get("name")}
        inst_outputs = node.get("outputs", [])
        inst_widgets = node.get("widgets_values", []) or []

        # Inject instance values / external links into the exposed body inputs.
        for ex in sg.get("inputs", []):
            name = ex.get("name")
            lid = (ex.get("linkIds") or [None])[0]
            bl = body_links.get(lid)
            if not bl or bl.get("origin_id") != -10:
                continue
            tnode = body_nodes.get(bl.get("target_id"))
            tslot = bl.get("target_slot")
            if not tnode or not (0 <= tslot < len(tnode.get("inputs", []))):
                continue
            target_name = tnode["inputs"][tslot].get("name")
            if not target_name:
                continue
            target_id = str(idmap[bl["target_id"]])

            inst_inp = inst_inputs.get(name)
            top_link_id = inst_inp.get("link") if inst_inp else None

            value = None
            if name == "prompt" and prompt_text:
                value = prompt_text
            elif name == "width" and width is not None:
                value = width
            elif name == "height" and height is not None:
                value = height
            elif name in ("noise_seed", "seed") and seed is not None:
                value = seed
            elif duration is not None and (
                name in ("value_1", "duration", "duration_sec", "seconds")
                or ex.get("label") == "duration"
            ):
                value = duration
            elif top_link_id is not None:
                for l in links:
                    if l and l[0] == top_link_id:
                        value = [str(l[1]), l[2]]
                        break
            elif name in widget_pos:
                pos = widget_pos[name]
                if pos < len(inst_widgets):
                    value = inst_widgets[pos]

            if value is None:
                continue
            if isinstance(value, str) and value in CONTROL_AFTER_GENERATE_VALUES:
                continue
            overrides[(target_id, target_name)] = value

        # Copy body nodes with remapped ids and re-linked inputs/outputs.
        for bn in sg.get("nodes", []):
            nb = dict(bn)
            nb["id"] = idmap[bn["id"]]
            if nb.get("inputs"):
                nb["inputs"] = [dict(i) for i in nb["inputs"]]
                for i in nb["inputs"]:
                    if i.get("link") is not None and i["link"] in link_idmap:
                        i["link"] = link_idmap[i["link"]]
            if nb.get("outputs"):
                nb["outputs"] = [dict(o) for o in nb["outputs"]]
                for o in nb["outputs"]:
                    if o.get("links"):
                        o["links"] = [link_idmap.get(lk, lk) for lk in o["links"]]
            new_nodes.append(nb)

        # Copy internal body links, skipping the -10/-20 boundary nodes.
        for bl in sg.get("links", []):
            oid = bl.get("origin_id")
            tid = bl.get("target_id")
            if oid in (-10, -20) or tid in (-10, -20):
                continue
            final_links.append([
                link_idmap[bl["id"]], idmap[oid], bl.get("origin_slot"),
                idmap[tid], bl.get("target_slot"), bl.get("type"),
            ])

        # Rewire the instance's top-level output links to the body output node.
        for j, exo in enumerate(sg.get("outputs", [])):
            lid = (exo.get("linkIds") or [None])[0]
            bl = body_links.get(lid)
            if not bl or bl.get("target_id") != -20:
                continue
            if j < len(inst_outputs):
                for outlink in (inst_outputs[j].get("links") or []):
                    link_rewrite[outlink] = (idmap[bl["origin_id"]], bl.get("origin_slot"))

    # Rebuild the top-level links: apply output rewires, drop links that
    # reference a removed subgraph instance.
    for l in links:
        if not l:
            continue
        if l[0] in link_rewrite:
            l[1], l[2] = link_rewrite[l[0]]
        if l[1] in removed_targets or l[3] in removed_targets:
            continue
        final_links.append(l)

    return {"nodes": new_nodes, "links": final_links}, overrides


def convert_ui_to_api_prompt(ui_data, prompt_text=None, negative_prompt=None, width=None, height=None, seed=None, input_image_name=None, overrides=None):
    """Convert UI format workflow JSON to API prompt dictionary and override parameters."""
    links = {link[0]: link for link in ui_data.get('links', [])}
    nodes = ui_data.get('nodes', [])

    api_prompt = {}

    for node in nodes:
        node_id = str(node['id'])
        class_type = node['type']
        
        if "Note" in class_type or class_type == "MarkdownNote":
            continue

        inputs_def = node.get('inputs', [])
        widgets = node.get('widgets_values', [])
        
        node_inputs = {}
        
        # Link-based inputs.
        for inp in inputs_def:
            name = inp['name']
            link_id = inp.get('link')
            if link_id is not None and link_id in links:
                link = links[link_id]
                origin_node_id = str(link[1])
                origin_slot = link[2]
                node_inputs[name] = [origin_node_id, origin_slot]

        # Widget-based inputs (copied for EVERY node so required loader
        # parameters such as clip_name / vae_name / unet_name are preserved).
        widget_inputs = map_widget_values(inputs_def, widgets)
        for k, v in widget_inputs.items():
            if k not in node_inputs:
                node_inputs[k] = v

        if class_type in ["LoadImage", "ETN_LoadImageBase64"]:
            if input_image_name:
                node_inputs["image"] = input_image_name
            elif len(widgets) > 0 and widgets[0] is not None:
                node_inputs["image"] = widgets[0]

        elif class_type in ["CLIPTextEncode", "CLIPTextEncodeSDXL", "WanTextEncode"]:
            is_negative = False
            current_text = str(widgets[0]) if len(widgets) > 0 else ""
            if any(neg_kw in current_text.lower() for neg_kw in ["low quality", "bad anatomy", "blurry", "deformed"]):
                is_negative = True

            if is_negative and negative_prompt:
                node_inputs["text"] = negative_prompt
            elif not is_negative and prompt_text:
                node_inputs["text"] = prompt_text
            else:
                node_inputs["text"] = current_text

        elif class_type in ["EmptyLatentImage", "EmptySD3LatentImage"]:
            node_inputs["width"] = width if width else (widgets[0] if len(widgets) > 0 else 512)
            node_inputs["height"] = height if height else (widgets[1] if len(widgets) > 1 else 512)
            node_inputs["batch_size"] = widgets[2] if len(widgets) > 2 else 1

        elif class_type in ["KSampler", "WanVideoSampler"]:
            node_inputs["seed"] = seed if seed is not None else random.randint(1, 1000000000)
            if len(widgets) > 2 and isinstance(widgets[2], (int, float)): node_inputs["steps"] = int(widgets[2])
            if len(widgets) > 3 and isinstance(widgets[3], (int, float)): node_inputs["cfg"] = float(widgets[3])

        elif class_type in ["SaveImage", "VHS_VideoCombine", "SaveVideo"]:
            node_inputs["filename_prefix"] = "ComfyUI_Agent"

        api_prompt[node_id] = {
            "class_type": class_type,
            "inputs": node_inputs
        }

    # Subgraph-exposed inputs take precedence over widget/link resolution.
    if overrides:
        for (node_id, input_name), value in overrides.items():
            if node_id in api_prompt:
                api_prompt[node_id]["inputs"][input_name] = value

    return api_prompt

def execute_prompt(workflow_api):
    client_id = str(uuid.uuid4())
    payload = json.dumps({"prompt": workflow_api, "client_id": client_id}).encode('utf-8')

    headers = get_comfy_headers()
    headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(f"{get_comfy_base_url()}/prompt", data=payload, headers=headers)
    with urllib.request.urlopen(req, timeout=60) as resp:
        res = json.loads(resp.read())

    prompt_id = res['prompt_id']
    print(f"Prompt queued! Prompt ID: {prompt_id}")

    start_time = time.time()
    while True:
        try:
            h_req = urllib.request.Request(
                f"{get_comfy_base_url()}/history/{prompt_id}", headers=get_comfy_headers()
            )
            with urllib.request.urlopen(h_req, timeout=30) as h_resp:
                history = json.loads(h_resp.read())
                if prompt_id in history:
                    print("Execution completed successfully!")
                    return prompt_id, history[prompt_id]
        except Exception:
            pass

        time.sleep(2)
        if time.time() - start_time > 1800: # 30 mins for video
            raise TimeoutError("Timed out waiting for ComfyUI generation (1800s).")

def download_outputs(prompt_id, history_entry, output_dir="."):
    os.makedirs(output_dir, exist_ok=True)
    saved_files = []
    outputs = history_entry.get('outputs', {})

    for node_id, node_output in outputs.items():
        if 'images' in node_output:
            for img in node_output['images']:
                params = urllib.parse.urlencode({"filename": img['filename'], "subfolder": img['subfolder'], "type": img['type']})
                v_req = urllib.request.Request(f"{get_comfy_base_url()}/view?{params}", headers=get_comfy_headers())
                with urllib.request.urlopen(v_req, timeout=60) as resp:
                    data = resp.read()
                out_path = os.path.join(output_dir, img['filename'])
                with open(out_path, "wb") as f:
                    f.write(data)
                saved_files.append(os.path.abspath(out_path))

        if 'gifs' in node_output or 'videos' in node_output:
            video_list = node_output.get('gifs', []) + node_output.get('videos', [])
            for vid in video_list:
                params = urllib.parse.urlencode({"filename": vid['filename'], "subfolder": vid['subfolder'], "type": vid['type']})
                v_req = urllib.request.Request(f"{get_comfy_base_url()}/view?{params}", headers=get_comfy_headers())
                with urllib.request.urlopen(v_req, timeout=60) as resp:
                    data = resp.read()
                out_path = os.path.join(output_dir, vid['filename'])
                with open(out_path, "wb") as f:
                    f.write(data)
                saved_files.append(os.path.abspath(out_path))

    return saved_files

def main():
    parser = argparse.ArgumentParser(description="ComfyUI Media Generator Engine for AI Agent")
    parser.add_argument("--list", action="store_true", help="List available workflows")
    parser.add_argument("--workflow", type=str, help="Name or path of specific workflow JSON file")
    parser.add_argument("--media-type", choices=["image", "video", "i2v"], help="Filter or target media type")
    parser.add_argument("--input-image", type=str, help="Path to input reference image for Image-to-Video (i2v)")
    parser.add_argument("--prompt", type=str, help="Positive prompt text")
    parser.add_argument("--negative-prompt", type=str, help="Negative prompt text")
    parser.add_argument("--width", type=int, help="Output image width")
    parser.add_argument("--height", type=int, help="Output image height")
    parser.add_argument("--seed", type=int, help="Random seed value")
    parser.add_argument("--duration", type=float, help="Video duration in seconds (overrides the workflow default)")
    parser.add_argument("--output-dir", type=str, default=".", help="Directory to save generated media")
    parser.add_argument("--host", type=str, help="Override ComfyUI server host[:port] (env: COMFYUI_HOST)")
    parser.add_argument("--scheme", type=str, choices=["http", "https"], help="Override URL scheme (env: COMFYUI_SCHEME)")
    parser.add_argument("--api-token", type=str, help="Bearer token for servers with auth (env: COMFYUI_API_TOKEN)")

    args = parser.parse_args()

    # CLI overrides take precedence over environment variables.
    if args.host:
        os.environ["COMFYUI_HOST"] = args.host
    if args.scheme:
        os.environ["COMFYUI_SCHEME"] = args.scheme
    if args.api_token:
        os.environ["COMFYUI_API_TOKEN"] = args.api_token

    workflows = scan_workflows()

    if args.list:
        reachable = server_reachable()
        print("=== ComfyUI Server ===")
        print(f"  URL       : {get_comfy_base_url()}")
        print(f"  Status    : {'REACHABLE' if reachable else 'UNREACHABLE'}")
        print(f"  API token : {'set' if os.environ.get('COMFYUI_API_TOKEN') else 'none'}")
        print()
        print("=== Available ComfyUI Workflows ===")
        if not workflows:
            print("  (no workflows found)")
        for wf in workflows:
            src = "SERVER" if wf.get('source') == 'server' else "LOCAL"
            print(f"[{src}] [{wf['media_type'].upper()}] {wf['name']} -> {wf['path']}")
        return

    uploaded_image_name = None
    if args.input_image:
        uploaded_image_name = upload_image(args.input_image)
        if not args.media_type:
            args.media_type = "i2v"

    # Match the output resolution to the reference image when the caller did
    # not explicitly request a width / height.
    if args.input_image and (args.width is None or args.height is None):
        img_size = get_image_size(args.input_image)
        if img_size:
            auto_w, auto_h = compute_resolution_from_image(img_size[0], img_size[1])
            if auto_w and auto_h:
                if args.width is None:
                    args.width = auto_w
                if args.height is None:
                    args.height = auto_h
                print(f"Auto resolution from reference image ({img_size[0]}x{img_size[1]}) -> {args.width}x{args.height}")

    target_media = args.media_type or ("i2v" if uploaded_image_name else "image")

    target_wf = None
    if args.workflow:
        w = args.workflow.lower()
        for wf in workflows:
            name = wf.get('name', '').lower()
            path = wf.get('path', '').lower()
            # Match by exact name, exact server/local path, or when the name
            # is a substring of the given string (e.g. a full local path that
            # ends with the server-side workflow basename). This ensures the
            # (possibly remote) server entry is preferred over a local file.
            if w == name or w == path or (name and name in w) or (path and path in w):
                target_wf = wf
                break
        # Fall back to a real local file only when it was not resolved from the
        # server list (e.g. an offline-only workflow not present on the server).
        if not target_wf and os.path.exists(args.workflow):
            try:
                with open(args.workflow, 'r', encoding='utf-8') as _f:
                    _wf_type = classify_workflow(args.workflow, json.load(_f))
            except Exception:
                _wf_type = None
            target_wf = {"path": args.workflow, "media_type": _wf_type or target_media, "source": "local"}

    if not target_wf:
        matching = [wf for wf in workflows if wf['media_type'] == target_media]
        if matching:
            target_wf = matching[0]

    # Native API Builders fallback only when no valid UI workflow is available.
    # An uploaded input image must NOT force the native path when an i2v
    # workflow was explicitly selected (or auto-matched).
    if target_media == "i2v" and not target_wf:
        print(f"Building native MiniMax H3 Image-to-Video API workflow...")
        api_prompt = build_default_minimax_i2v_api(
            prompt_text=args.prompt,
            image_name=uploaded_image_name,
            seed=args.seed,
            width=args.width,
            height=args.height,
            duration_sec=args.duration if args.duration is not None else 5
        )
    elif target_media == "video" and not target_wf:
        print(f"Building native MiniMax H3 Text-to-Video API workflow...")
        api_prompt = build_default_minimax_t2v_api(
            prompt_text=args.prompt,
            seed=args.seed,
            width=args.width,
            height=args.height,
            duration_sec=args.duration if args.duration is not None else 5
        )
    else:
        if not target_wf:
            print("Error: No suitable workflow found.")
            return

        print(f"Selected Workflow: {target_wf['path']} (Type: {target_wf.get('media_type')}, Source: {target_wf.get('source')})")
        wf_data = load_workflow_data(target_wf)

        if isinstance(wf_data, dict) and "nodes" in wf_data:
            flat_wf, subgraph_overrides = flatten_subgraphs(
                wf_data,
                prompt_text=args.prompt,
                seed=args.seed,
                width=args.width,
                height=args.height,
                duration=args.duration,
            )
            api_prompt = convert_ui_to_api_prompt(
                flat_wf,
                prompt_text=args.prompt,
                negative_prompt=args.negative_prompt,
                width=args.width,
                height=args.height,
                seed=args.seed,
                input_image_name=uploaded_image_name,
                overrides=subgraph_overrides,
            )
        else:
            api_prompt = wf_data

    prompt_id, history_entry = execute_prompt(api_prompt)
    saved_files = download_outputs(prompt_id, history_entry, output_dir=args.output_dir)

    print("=== Generation Finished ===")
    for sf in saved_files:
        print(f"Saved: {sf}")

if __name__ == "__main__":
    main()
