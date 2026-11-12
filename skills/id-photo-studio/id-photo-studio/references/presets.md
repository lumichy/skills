# 証明写真 規格プリセット・AIプロンプト集

## 1. 主要な証明写真の規格一覧（日本国内・国際規格）

すべて **300 DPI**（または高精細 **350〜600 DPI**）でのピクセル換算値を基準とします。
`scripts/process_id_photo.py` では以下のプリセット名（`--preset`）を直接指定できます。

| プリセットID | 用途 | サイズ (縦×横 mm) | 300 DPI (縦×横 px) | 頭頂余白の目安 | 顔サイズ（頭頂〜顎）の目安 | 推奨背景色 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `resume` | 履歴書・転職・一般資格試験 | 40 × 30 mm | 472 × 354 px | 4〜6 mm (約12%) | 24〜28 mm (約65%) | 白・青（水色）・グレー |
| `mynumber` | マイナンバーカード・パスポート | 45 × 35 mm | 531 × 413 px | 4 ± 2 mm (約9%) | 34 ± 2 mm (約75%) | 白・薄い青・薄いグレー（無地均一） |
| `passport` | パスポート（旅券・国際規格） | 45 × 35 mm | 531 × 413 px | 4 ± 2 mm (約9%) | 34 ± 2 mm (約75%) | 白または薄い単色（影なし） |
| `license` | 運転免許証 | 30 × 24 mm | 354 × 283 px | 2〜4 mm (約10%) | 18〜22 mm (約65%) | 青・白・グレー |
| `toeic` | TOEIC・英検・Web出願全般 | 40 × 30 mm | 472 × 354 px | 4〜6 mm (約12%) | 24〜28 mm (約65%) | 白・青・グレー |
| `us_visa` | 米国ビザ・グリーンカード | 51 × 51 mm | 600 × 600 px | 6〜10 mm (約15%) | 25〜35 mm (50〜69%) | 白（完全な白 `#FFFFFF`） |
| `custom` | カスタムサイズ（`--width-mm`, `--height-mm` 指定） | 任意 | 自動計算 | 約12% | 約65% | 用途に応じる |

---

## 2. 標準背景カラーコード一覧

`scripts/process_id_photo.py` の `--bg-color` や AI 生成時の背景指定で使用する標準色です。

- `white` (`#FFFFFF`): パスポート・マイナンバー・米国ビザ・清潔感重視の履歴書
- `blue` (`#D4E6F6`): 日本の履歴書・運転免許証で最も一般的な爽やかなライトブルー
- `gray` (`#E6E8EA`): 落ち着いた印象を与えるライトグレー
- `navy_grad` (`#2B4C7E` → `#4A6FA5`): 役員・エグゼクティブプロフィール等（公的証明書には不可）

> **注意**: パスポートやマイナンバーカード等の公的証明書では、グラデーション背景や背景の影は不備（却下）の原因となるため、必ず均一な単色（`white` または薄い `blue` / `gray`）を使用してください。

---

## 3. 画像生成・編集AI用プロンプトテンプレート（汎用）

人物写真を証明写真化する際、本人の顔立ち（アイデンティティ）を完全に維持することが最優先です。利用可能な画像編集AI（組み込みの画像生成・編集ツール、MCPサーバー、外部画像編集API等）に対して、以下のテンプレートを状況に合わせて調整して渡してください。

### パターンA：私服からスーツへの着せ替え＋証明写真スタジオ風補正（履歴書・転職・マイナンバー等）

```text
Edit the reference photo at <INPUT_IMAGE_PATH> to create a professional Japanese official ID photo (証明写真) and save it to <TEMP_AI_IMAGE_PATH>.

Strict Requirements:
1. Identity Preservation: Keep the exact same facial features, eye shape, nose, mouth, skin tone, facial structure, and age of the person in the input photo. Do NOT alter their identity or make them look like a different person.
2. Posture & Gaze: Adjust the body posture so the shoulders are square, level, and facing straight forward. The head must be straight and centered, looking directly at the camera with a natural, polite, closed-mouth expression.
3. Attire: Replace the clothing with a neat, professional dark navy or charcoal business suit, a crisp white collared dress shirt, and (if appropriate) a conservative business tie.
4. Hair & Grooming: Keep the original hairstyle, tidying up only stray flyaway hairs so the eyebrows, eyes, and facial contours are clearly visible.
5. Lighting & Background: Apply soft, even studio portrait lighting with no harsh shadows on the face or background. Use a completely solid, uniform <BG_COLOR_DESCRIPTION> background.
6. Framing: Frame as a head-and-shoulders portrait with ample margin above the top of the head and below the chest so it can be precisely cropped later.
```

### パターンB：服装はそのまま維持し、背景・照明・姿勢のみ証明写真化

```text
Edit the reference photo at <INPUT_IMAGE_PATH> to create an official ID photo (証明写真) and save it to <TEMP_AI_IMAGE_PATH>.

Strict Requirements:
1. Identity & Clothing Preservation: Keep the exact same person's facial features, expression, and current clothing. Tidy up minor wrinkles if needed.
2. Posture & Alignment: Center the head and level the shoulders so the subject faces straight forward toward the camera.
3. Lighting & Background: Remove uneven lighting or shadows on the face, and replace the background with a completely flat, solid, shadow-free <BG_COLOR_DESCRIPTION> background.
4. Framing: Include enough headroom above the hair and chest area below the chin for subsequent exact millimeter cropping.
```

### パターンC：人物・顔の表情は一切変えず、影（照明）・背景・服装のみ変更

元の写真の表情（笑顔や口元・目線など）や顔立ちを1ミリも変えたくない場合（AIによる顔の再描画で雰囲気が変わるのを防ぎたい場合）に使用します。

```text
Edit the reference photo at <INPUT_IMAGE_PATH> to create an ID photo (証明写真) and save it to <TEMP_AI_IMAGE_PATH>.

Strict Requirements:
1. Strict Face & Expression Lock (DO NOT MODIFY THE FACE): Keep the person's head, facial features, eyes, gaze, mouth, and exact facial expression 100% untouched and identical to the input photo. Do NOT alter, retouch, or regenerate their expression or facial structure in any way.
2. Lighting & Shadow Removal: Remove any uneven shadows or harsh lighting casts on the face and neck so the illumination looks clean and balanced, without changing the facial pixels or expression.
3. Attire Replacement Only: Replace only the clothing below the neck with <ATTIRE_DESCRIPTION> (e.g., a neat dark business suit and crisp white collared shirt, or simple formal wear), naturally aligned with the neck.
4. Background Replacement: Replace the background with a completely flat, solid, uniform, shadow-free <BG_COLOR_DESCRIPTION> background.
5. Framing: Frame as a centered head-and-shoulders bust portrait with ample headroom above the top of the head and chest area below the chin so it can be precisely cropped later.
```

---

## 4. コンビニプリント（L判・2L判）の仕様と注意点

- **L判サイズ**: `89 × 127 mm`（300 DPI で `1051 × 1500 px`）
- **2L判サイズ**: `127 × 178 mm`（300 DPI で `1500 × 2102 px`）
- **コンビニマルチコピー機での印刷時の注意**:
  - セブン-イレブン、ファミリーマート、ローソン等の写真プリントで印刷する際、デフォルトでは「フチなし印刷（画像を数％拡大して裁断）」になる場合があります。
  - 拡大されると証明写真のミリ単位のサイズが狂うため、ユーザーには必ず **「プリント時に『フチあり印刷（縮小して全体を入れる）』を選択するか、印刷後に定規で実寸を確認してください」** と案内してください。
  - `process_id_photo.py` はこの拡大リスクも考慮し、シート周囲に十分な余白と10mmスケール目盛り（実寸確認用ゲージ）、およびカッター用のトンボ（トリムマーク）を自動描画します。

