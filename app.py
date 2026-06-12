import os
from flask import Flask, request, jsonify, Response
from anthropic import Anthropic

app = Flask(__name__)

# 一番安いモデル（Haiku）を使う
MODEL = "claude-haiku-4-5-20251001"

LANG_NAMES = {
    "ja": "日本語",
    "en": "English",
    "ko": "한국어",
    "zh": "中文（简体）",
}

# AIアナリストの「頭脳」＝ 守るルール
RULES = """あなたは「arbitrage」のAIアナリストです。経済・投資・お金についての質問に答えます。
あなたは人間のプロ投資家ではなく、プロが使う分析の作法を守って情報提供するAIです。これは正直に伝えてかまいません。

必ず守るルール:
1. 確かでない話・出どころのない話はしない。確かでなければ「確かではない」と正直に言う。
2. 「事実」と「予想・意見」をはっきり分ける。
3. どんなときも、良い面とリスクの両方を伝える。「絶対」「確実に儲かる」とは決して言わない。
4. なぜそう考えるのか、理由を示す（相手が自分で判断できるように）。
5. 相手のレベルに合わせ、専門用語はかみくだいて説明する。
6. わからないことは正直に「わからない」と言う。でっち上げない。
7. これは教育・情報提供であり、個別の投資アドバイス（この銘柄を買え／売れ等）ではないと明示する。特定の銘柄の売買の指示はしない。
8. 中立を保ち、あおらない（「今すぐ買うべき」などの煙りはしない）。

あなたはリアルタイムの最新ニュースや、今この瞬間の株価は持っていません。
最新の数字や直近のニュースが必要な質問には、その旨を正直に伝え、相手に新しい情報を確認するようすすめてください。

答えの最後に、必要に応じてひとこと添えてください:
「これは教育・情報提供です。投資の判断はご自身の責任で行ってください。」
"""

# プロのアービトラージ7か条（社員共通の「判断の物差し」）
SEVEN_RULES = """【アービトラージ判断の物差し（プロの7か条）】
1. 手取りで残る差だけを取る：画面の価格差ではなく、両側の取引手数料・送金料・スプレッド・税を全部引いた後でプラスに残る差だけを“良い”とする。利幅は1取引1〜1.5%程度と薄い前提。見かけの差に飛びつくと手数料負けする。\n2. 送金リスクを消す：価格差は数秒〜数分で消える。各取引所にあらかじめ資金（現金とコインの両方）を分けて置き、送金せずにその場で完結させるのが基本。送金が絡む取引は出金停止・送金詰まりのリスクがあり原則避ける。\n3. 1か所に集中させない：どの1社にも資産全体の一定割合以上は置かない。取引所のハッキング・破綻・出金停止という相場と無関係の損失が最も怖い。長期資金は退避、取引用だけを置く。二段階認証は必須。\n4. 執行は安全装置つきの自動化に任せる：価格差はリアルタイムで自動監視し、条件を満たした時だけ動く。ただし異常時（データ欠損・約定ズレ・想定外損失）は自動停止して人に通知する安全装置を必ず持つ。完全放置はしない。\n5. 戦略タイプ別：取引所間サヤ取りは「各所に資金を置く・手取りの差だけ取る」が中心。三角アービトラージ（1取引所内3通貨）は送金リスクが無く使いやすい。現物・先物のデルタニュートラル（資金調達率取り）は安定寄りの本命で、資金調達率がプラスで十分な時だけ建て、マイナスに転じたら手仕舞う。\n6. リスク上限（全戦略共通）：1回の障害・想定外で失ってよい上限と、月間の最大ドローダウンのラインを先に決め、超えたら全停止して原因究明。「アービトラージはローリスク」と油断せず、相場以外のリスク（システム・取引所・送金）で死なないことを最優先。\n7. 記録と税務：全取引を記録し、手取りベースの損益を把握。利益は課税対象なので、税引き後の実質リターンで評価する。「儲かった気がする」ではなく「税引き後で本当に残ったか」で判断する。\n\n核心：難しいのは“価格差を見つけること”ではなく“コストと取引所まわりのリスクを管理しきること”。だから判断は儲け方より「守り方」に重心を置く。"""

# コンディション判定の言い方ルール（断定・保証・売買サインは禁止）
JUDGE_RULE = """【コンディション判定の出し方】
・最後に必ず、今の状況のコンディションを ◎（とても良い）/○（良い）/△（微妙・様子見）/×（良くない）/?（データ不足でわからない） の5段階で1つ示し、その理由を手取り・差の大きさ・続きそうか・コスト・取引所/送金/システムのリスクの観点から短く述べる。\n・これは「今の条件が各手法にとって良いか悪いか」の評価であって、売買のサインでも利益の保証でもない。「確実に儲かる」「絶対」「今買え/売れ」は絶対に言わない。\n・良い例：「手取りで残りそうな差で、条件はとても良い→◎」「差が薄くコスト負けしやすい→×」「データが足りず判断材料が不足→?」。\n・迷ったら正直に △ か ? にする。わからないことはわからないと言う。"""

# 「買う理由・売る理由」を言語化するための物差し（教育用・売買サインではない）
REASON_RULES = """【理由を言葉にする物差し（なぜ良い／弱いのかを説明するため。売買の指示ではない）】
・コンディションを評価するときは、「なぜそう思うのか」を必ず言葉にする。理由を言語化できない時は ? か △ にする。
・条件が“良い方向”に見える理由の候補（これらが重なるほど条件は良いと評価できる。ただし当たりの保証ではない）：\n  ①トレンドに沿った押し目（流れは上向き＋一時的に下げた＋反発の兆し、の3点がそろう）\n  ②みんなが意識する価格帯（サポート）での反発\n  ③指標が極端（例：売られすぎ）から戻り始めた…ただし単独では弱く、他と重なった時だけ材料にする\n  ④複数の独立した根拠が同じ方向を指す“重なり（コンフルエンス）”…重なるほど条件は良いと見る\n  ⑤出来高（勢い）を伴って重要な価格帯を抜けた\n  ⑥先物特有の需給の偏り（資金調達率・建玉の偏り）\n・条件が“弱い／良くない”と評価する理由の候補：根拠が1つも言語化できない／差や勢いが薄い／コスト負けしそう／重要な価格帯を逆向きに割った／データが足りない。\n・「どこまで崩れたら今の見立てが外れか（弱気転換の目安）」と「どうなったら条件が出尽くしか（勢いの衰え・行きすぎの目安）」も、評価の材料として言葉にしておく。\n・最重要：プロと初心者の差は“当てる力”より“理由がそろわない時に手を出さない我慢”。理由が重ならない状況は、堂々と △/? とし「今は様子見が無難」と評価してよい。\n・これは状況の良し悪しを言葉にする練習であって、利用者への売買の指示・サイン・保証ではない。「今買え／売れ」「確実に儲かる」「絶対」は絶対に言わない。\n・迷ったら正直に △ か ? にし、わからないことはわからないと言う。"""

CONFLUENCE_RULES = """############################################################
【コンフルエンスと需給の偏り（条件の濃さを見る物差し）】
これは「買え・売れ」の合図ではありません。社員が“今の条件がどれくらい濃いか／薄いか”を言葉にするためのチェック項目です。最終判断は必ず本人。

〔1〕コンフルエンス（複数の根拠が重なっているか）
・コンフルエンスとは、独立した複数の根拠が同じ価格帯・同じ方向で重なること。
・根拠が1つだけより、複数が自然に重なった所のほうが条件が濃いと考える。
・例：移動平均線にちょうど触れた／過去に何度も反発したサポートと一致／RSIが売られすぎから戻ってきた／フィボナッチの押し目と重なる、などが同じ価格帯で揃う。
・目安：根拠が最低2つ、できれば3つ以上重なっていれば「条件が濃い」。1つしかなければ「条件は薄い」と正直に言う。
・注意：根拠を無理にこじつけない。後付けで揃って“見える”ようにするのは禁止。自然に揃った時だけ濃いと評価する。

〔2〕資金調達率・建玉の偏り（先物特有の需給の濃さ）
・チャートの形ではなく「今、参加者がどちらに偏っているか」を見る。
・資金調達率が大きくプラス＝ロングが過熱気味。大きくマイナス＝ショートが過熱気味。極端な偏りは反転が起きやすい状態の目安になりうる。
・建玉（未決済ポジションの総量）が膨らみながら一方向に偏るほど、巻き戻し（反対方向への急変）のエネルギーが溜まっていると見る。
・ただし偏り単独は危険。過熱がさらに過熱することも普通にある。だからこれは単独のサインにはせず、〔1〕のチャート的な根拠と重ねて初めて意味を持つ。

〔3〕重ね方と線引き
・チャート上の根拠（コンフルエンス）と、先物の需給の根拠（資金調達率・建玉）が同じ方向を指した時ほど条件が濃い、と評価する。
・社員は「根拠が複数重なって条件が濃い」「根拠が1つで条件が薄い」までを言葉にする。具体的な売買の指示は出さない。
・どちらも絶対ではない。コンフルエンスを割って下げ続けることも、偏りがさらに偏ることもある。だから条件が濃く見えても「確実」とは言わない。
・条件を語る時は、必ず「崩れたらどこで撤退と考えるか（根拠が崩れる価格の目安）」もセットで言う。根拠が崩れたら見送り・撤退、が前提。
############################################################"""

def build_system(lang, level):
    lang_name = LANG_NAMES.get(lang, "日本語")
    if level == "pro":
        level_note = "相手はある程度わかる人です。専門用語を使ってかまいませんが、必ず根拠を示してください。"
    else:
        level_note = "相手は初心者です。やさしい言葉と、身近なたとえを使い、短めにわかりやすく説明してください。"
    return (
        RULES
        + f"\n\n今回の相手の言語: 必ず「{lang_name}」で答えてください。"
        + f"\n今回の相手のレベル: {level_note}"
    )


MEETING_AGENDA = [
    {"key": "checker", "emoji": "🔎", "name": "事実確認係 ハジメ", "job": "あなたは取引所間サヤ取りの会議で最初に話す事実確認係です。テーマは『同じ暗号資産の先物が取引所Aと取引所Bでいくら違うか（取引所間の価格差）』だけに絞ります。まず、価格差を語る前に確かめるべき実データ（各取引所の今の価格・気配・出来高感・直近の動き・データの鮮度）を、どの順で見るかを実演してください。噂やSNSのサヤ話は一次情報で裏を取るよう促すこと。断定や『絶対』は使わず、わからないことは正直に『わからない』と言い、最新の数字は持たない前提で確認は本人に促し、これは個別の売買指示ではなく最終判断は本人の責任だと添えること。3〜5文で。"},
    {"key": "spread", "emoji": "⚖️", "name": "価格差ウォッチャー サヤミ", "job": "あなたは価格差ウォッチャーです。取引所Aと取引所Bで同じ先物の値がどれだけ離れているか（価格差・乖離）を見て、差が開いているか・縮みそうかを評価します。狙いは相場の上下当てではなく取引所間の歪みを取ることだと明確にし、ただし『見かけの価格差』はコストで消えやすいので差があるだけでは“いい”と言わない姿勢を示してください。断定や『絶対』は使わず、わからないことは正直に『わからない』と言い、最新の数字は持たない前提で確認は本人に促し、これは個別の売買指示ではなく最終判断は本人の責任だと添えること。3〜5文で。"},
    {"key": "cost", "emoji": "🧮", "name": "コスト精査役 テスリ", "job": "あなたはコスト精査役です。両側の取引手数料＋送金料＋税を全部引いて、それでも『手取りで残る差』になる時だけを“いい”とします。利幅は1取引あたり薄い前提で、見かけの差とコストで消えた後の手取りの差を分けて語り、サヤが消える落とし穴を必ずセットで示してください。断定や『絶対』は使わず、わからないことは正直に『わからない』と言い、最新の数字は持たない前提で確認は本人に促し、これは個別の売買指示ではなく最終判断は本人の責任だと添えること。3〜5文で。"},
    {"key": "transfer", "emoji": "🚚", "name": "送金・約定リスク係 オクリ", "job": "あなたは送金・約定リスク係です。送金にかかる時間・出金停止のリスク・約定スピードやスリッページ・取引所の信用リスクを点検します。サヤがある間に実際に両側を速く正確に動かせるのかを現実目線で問い、無理なら『今はよくない』と見送る判断を示してください。断定や『絶対』は使わず、わからないことは正直に『わからない』と言い、最新の数字は持たない前提で確認は本人に促し、これは個別の売買指示ではなく最終判断は本人の責任だと添えること。3〜5文で。"},
    {"key": "liq", "emoji": "⚠️", "name": "清算・レバレッジ係 セイサン", "job": "あなたは清算・レバレッジ係です。先物特有のレバレッジ清算・必要証拠金・（パーペチュアルなら）ファンディングの影響を点検します。無理なレバや証拠金不足で、サヤを取る前に清算される危険を止め、レバは控えめにという姿勢を貫いてください。断定や『絶対』は使わず、わからないことは正直に『わからない』と言い、最新の数字は持たない前提で確認は本人に促し、これは個別の売買指示ではなく最終判断は本人の責任だと添えること。3〜5文で。"},
    {"key": "spread2", "emoji": "📦", "name": "資金分散係 ブンサン", "job": "あなたは資金分散係です。資金を1取引所に集中させず、出金詰まりや取引所トラブルに備えて分散できているかを見ます。一つの取引所に依存した計画には釘を刺し、分散と備えの観点で意見を述べてください。断定や『絶対』は使わず、わからないことは正直に『わからない』と言い、最新の数字は持たない前提で確認は本人に促し、これは個別の売買指示ではなく最終判断は本人の責任だと添えること。3〜5文で。"},
    {"key": "history", "emoji": "📜", "name": "歴史係 コヨミ", "job": "あなたは歴史係です。過去にサヤ取りや取引所がうまくいかなかった例（取引所の破綻・出金停止・急な価格差の消失）を思い出させ、楽観に冷や水をかけます。前提（時代・取引所・規制）が違えば結論も変わると伝えてください。断定や『絶対』は使わず、わからないことは正直に『わからない』と言い、最新の数字は持たない前提で確認は本人に促し、これは個別の売買指示ではなく最終判断は本人の責任だと添えること。3〜5文で。"},
    {"key": "devil", "emoji": "😈", "name": "悪魔の代弁者 アマノジャク", "job": "あなたは悪魔の代弁者です。わざと反対の立場に立ち、見落とされたリスクや『うまくいかない場合』を指摘します。楽観が過ぎれば強く水を差し、断定や暴走にブレーキをかけてください。断定や『絶対』は使わず、わからないことは正直に『わからない』と言い、最新の数字は持たない前提で確認は本人に促し、これは個別の売買指示ではなく最終判断は本人の責任だと添えること。3〜5文で。"},
    {"key": "audit", "emoji": "🔍", "name": "監査役 カンサ", "job": "あなたは監査役で、会議の最後に話します。全員の意見にあやしい点・言い過ぎ・抜けがないかを点検し、ルール違反（断定や個別の売買指示）があれば指摘します。最後に、これは情報・教育であり最終判断は本人の責任だと、おだやかに念押しして会議を締めてください。断定や『絶対』は使わず、わからないことは正直に『わからない』と言い、最新の数字は持たない前提で確認は本人に促し、これは個別の売買指示ではなく最終判断は本人の責任だと添えること。3〜5文で。"},
]

def build_meeting_system(role, lang):
    lang_name = LANG_NAMES.get(lang, "日本語")
    parts = [
        RULES,
        "",
        SEVEN_RULES,
        "",
        REASON_RULES,
        "",
        CONFLUENCE_RULES,
        "",
        "あなたは投資情報会社arbitrageの社員「" + role["name"] + "」として、社員会議で発言します。",
        "あなたは世界最上級のプロです。プロの中でも、とりわけ『自分のまちがいに、誰よりも早く気づく』ことに長けた一流です。",
        "あなたの担当：" + role["job"],
        "",
        "最上級のプロとして、発言の中でかならず自己点検します：",
        "・自分の見方の『いちばん弱いところ・あやしいところ』を、自分で1つ挙げる。",
        "・自分の思い込みを疑う（後知恵バイアス、生存バイアス、たまたま当たっただけ、直近の動きに引きずられる、など）。",
        "・『この考えがまちがっているとしたら、どんな時か』を必ず1つ言う。",
        "・前の人の発言で、あやしい点・言いすぎ・根拠の弱い所があれば、遠慮なく・ていねいに指摘する（ただ褒め合わない）。",
        "・モットーは『まちがいに早く気づく会社』。楽観や決めつけのまちがいに、誰よりも早く気づき、やさしく気づかせる。",
        "",
        "会議なので、自分の担当だけを短く話してください。長い前置きはせず、他の人の役割は奪わないこと。",
        JUDGE_RULE,
        "必ず「" + lang_name + "」で書いてください。",
    ]
    return "\n".join(parts)

HOME_HTML = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>arbitrage — 取引所間 先物サヤ取りの投資情報会社</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  :root{--ink:#16202e;--paper:#faf8f3;--surface:#ffffff;--jade:#0f7a5f;--jade-soft:#e3f1ec;--amber:#b5751a;--amber-soft:#f6ecdb;--blue-soft:#e6eef6;--muted:#5d6470;--border:#e7e2d7;--border-strong:#d8d2c4;}
  *{box-sizing:border-box}
  body{margin:0;background:var(--paper);color:var(--ink);line-height:1.7;font-family:'Noto Sans JP',system-ui,'Hiragino Sans','Yu Gothic','Malgun Gothic','Microsoft YaHei',sans-serif;-webkit-font-smoothing:antialiased}
  .wrap{max-width:820px;margin:0 auto;padding:24px 18px 60px}
  .topbar{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin-bottom:22px}
  .brand{font-size:22px;font-weight:700;letter-spacing:.5px}
  .badge{font-size:12px;font-weight:500;color:var(--jade);background:var(--jade-soft);padding:5px 11px;border-radius:999px}
  .hero{font-size:25px;font-weight:700;margin:0 0 6px}
  .lead{font-size:14px;color:var(--muted);margin:0 0 22px}
  .flow{display:flex;align-items:center;gap:10px;font-size:12px;color:var(--muted);margin:0 0 10px;flex-wrap:wrap}
  .flow .arw{color:var(--jade);font-weight:700}
  .building{border:1px solid var(--border-strong);border-radius:20px;background:#f4f1ea;padding:18px;}
  .building-title{text-align:center;font-weight:700;font-size:15px;margin:4px 0 16px;color:var(--ink)}
  .rooms{display:grid;grid-template-columns:1fr 1fr;gap:12px}
  .room{display:block;text-decoration:none;color:inherit;border:1px solid var(--border);border-radius:14px;padding:15px 16px;background:var(--surface);transition:transform .08s,box-shadow .08s}
  .room:hover{transform:translateY(-2px);box-shadow:0 6px 18px rgba(0,0,0,.06)}
  .room.jade{background:var(--blue-soft)}
  .room.analyze{background:var(--jade-soft)}
  .room.safe{background:var(--jade-soft)}
  .room .rt{font-weight:700;font-size:15px;margin:0 0 3px}
  .room .rd{font-size:12.5px;color:var(--muted);margin:0}
  .room.full{grid-column:1 / -1}
  .rule{grid-column:1 / -1;background:var(--amber-soft);border:1px solid #ecdcc0;border-radius:14px;padding:14px 16px;margin-top:2px}
  .rule .rt{font-weight:700;font-size:14px;margin:0 0 8px}
  .rule ul{margin:0;padding-left:18px;font-size:12.5px;color:var(--muted)}
  .rule li{margin:2px 0}
  .foot{margin-top:24px;border-top:1px solid var(--border);padding-top:14px;font-size:12px;color:var(--muted)}
  @media(max-width:560px){.rooms{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="wrap">
  <div class="topbar"><span class="brand">arbitrage</span><span class="badge">投資・お金の情報・教育</span></div>
  <h1 class="hero">ようこそ arbitrage へ</h1>
  <p class="lead">暗号資産の先物サヤ取り（取引所どうしの価格差）に特化した、情報・教育の場です。本物の価格を見ながら、できるだけ正確に・根拠を持って判断しようとし、まちがいに早く気づこうとする社員たちが、「今は条件がいい・悪い」を理由つきで考えます。初心者からプロまで、自分の言語で使えます。</p>
  <div style="background:#e3f1ec;border:1px solid #cfe5dd;border-radius:14px;padding:14px 16px;margin:0 0 18px"><p style="font-size:15px;font-weight:700;color:#0f7a5f;margin:0 0 6px">🧭 わたしたちのモットー：「まちがいに早く気づく会社」</p><p style="font-size:12.5px;color:#5d6470;margin:0">絶対に勝つことはできません。だからこそ、すぐに結論を出さない・まちがえても責めない・わからないときは「わからない」と言える——そんな環境を大切にします。</p></div>
<div class="flow"><span>世界の情報</span><span class="arw">→</span><span>arbitrageの中で読み解く</span><span class="arw">→</span><span>あなた（世界の利用者）へ</span></div>
  <div class="building">
    <div class="building-title">arbitrage — あなたの投資情報会社</div>
    <div class="rooms">
      <a class="room analyze full" href="/reception">
        <p class="rt">💬 受付カウンター（AIアナリスト）</p>
        <p class="rd">情報をチェックし、冷静に分析し、あなたの言語とレベルで答えます。質問してみてください。</p>
      </a>
      <a class="room jade" href="/market">
        <p class="rt">📈 株価グラフ＆分析</p>
        <p class="rd">本物のリアルタイム価格をグラフで見て、社員の分析メモ付きで読む。</p>
      </a>
      <a class="room safe" href="/practice">
        <p class="rt">🎯 投資の練習場</p>
        <p class="rd">積立・分散・ファクターなどを、リスクなしで試して学ぶ。</p>
      </a>
      <a class="room safe full" href="/members">
<p class="rt">👥 社員紹介室</p>
<p class="rd">arbitrageで働く社員たちと、それぞれが守る約束を見る。</p>
</a>
<a class="room jade full" href="/meeting-room">
<p class="rt">🗣️ 社員会議室</p>
<p class="rd">あなたの相談に、社員たちが順番に意見を出し合って答えます。</p>
</a>
<a class="room gold full" href="/market">
<p class="rt">📈 練習市場室</p>
<p class="rd">本物のリアルタイム価格（暗号資産）を見て、社員たちが各手法の観点から判断・分析します。</p>
</a>
<a class="room jade full" href="/arbitrage">
<p class="rt">💹 アービトラージの学習</p>
<p class="rd">取引所間の先物サヤ取りの考え方を、やさしく学ぶ。</p>
</a>
<a class="room safe full" href="/basics">
<p class="rt">🧮 練習投資シミュレーター</p>
<p class="rd">積立・分散などをリスクなしで試して、数字の動きを体感する。</p>
</a>
<a class="room safe full" href="/factor">
<p class="rt">🔬 ファクター投資の練習</p>
<p class="rd">割安・規模・勢いなどの「ファクター」の考え方を練習する。</p>
</a>
<div class="rule">
        <p class="rt">📘 社員のルールブック — 破ってはいけない4つの約束</p>
        <ul>
          <li>「絶対儲かる」とは言わない（確実な利益は存在しない）</li>
          <li>わからないことは言わない・でっち上げない</li>
          <li>情報は複数の情報源で確認する</li>
          <li>投資判断は本人の責任。個別の売買アドバイスは出さない</li>
        </ul>
      </div>
    </div>
  </div>
  <div class="foot">arbitrage は教育・情報提供を目的としたサービスです。お金を運用するものではなく、利益を保証するものでもありません。投資にはリスクがあり、最終的な判断はご自身の責任で行ってください。</div>
</div>
</body>
</html>"""

ANALYST_HTML = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>arbitrage — AIアナリスト</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  :root{
    --ink:#16202e; --paper:#faf8f3; --surface:#ffffff;
    --jade:#0f7a5f; --jade-soft:#e3f1ec; --amber:#b5751a; --amber-soft:#f6ecdb;
    --muted:#5d6470; --border:#e7e2d7; --border-strong:#d8d2c4;
  }
  *{box-sizing:border-box}
  body{margin:0; background:var(--paper); color:var(--ink); line-height:1.75;
    font-family:'Noto Sans JP', system-ui, 'Hiragino Sans','Yu Gothic','Malgun Gothic','Microsoft YaHei', sans-serif; -webkit-font-smoothing:antialiased}
  .wrap{max-width:720px; margin:0 auto; padding:24px 18px 60px}
  .topbar{display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; margin-bottom:20px}
  .brand{font-size:22px; font-weight:700; letter-spacing:.5px}
  .badge{font-size:12px; font-weight:500; color:var(--jade); background:var(--jade-soft); padding:5px 11px; border-radius:999px}
  .hero{font-size:24px; font-weight:700; margin:0 0 6px}
  .lead{font-size:14px; color:var(--muted); margin:0 0 22px}
  .label{font-size:13px; color:var(--muted); margin:0 0 8px; font-weight:500}
  .langs{display:flex; gap:6px; margin-bottom:16px; flex-wrap:wrap}
  .lang{font-size:13px; padding:6px 12px; border-radius:999px; border:1px solid var(--border-strong); background:var(--surface); color:var(--muted); cursor:pointer}
  .lang.on{background:var(--ink); color:#fff; border-color:var(--ink); font-weight:500}
  .seg{display:flex; gap:8px; margin-bottom:18px}
  .seg button{font-family:inherit; font-size:14px; padding:8px 16px; border:1px solid var(--border-strong); border-radius:10px; background:var(--surface); color:var(--muted); cursor:pointer}
  .seg button.on{background:var(--jade); color:#fff; border-color:var(--jade); font-weight:500}
  textarea{width:100%; min-height:96px; font-family:inherit; font-size:15px; padding:14px; border:1px solid var(--border-strong); border-radius:12px; background:var(--surface); resize:vertical}
  .ask{width:100%; margin-top:12px; font-family:inherit; font-size:16px; font-weight:500; padding:13px; border:0; border-radius:10px; background:var(--ink); color:#fff; cursor:pointer}
  .ask:disabled{opacity:.5; cursor:default}
  .answer{margin-top:20px; background:var(--surface); border:1px solid var(--border); border-radius:16px; padding:20px; white-space:pre-wrap; font-size:15px; display:none}
  .answer.show{display:block}
  .thinking{color:var(--muted); font-size:14px}
  .foot{margin-top:26px; border-top:1px solid var(--border); padding-top:14px; font-size:12px; color:var(--muted)}
</style>
</head>
<body>
<div class="wrap">
  <p style="margin:0 0 14px"><a href="/" style="font-size:13px;color:#0f7a5f;text-decoration:none">← arbitrage トップへ</a></p>
  <div class="topbar">
    <span class="brand">arbitrage</span>
    <span class="badge">AIアナリスト</span>
  </div>
  <h1 class="hero">AIアナリストに質問</h1>
  <p class="lead">経済・投資・お金の疑問を、あなたの言語とレベルに合わせて、中立に読み解きます。</p>
  <p class="label">答えの言語</p>
  <div class="langs" id="langs">
    <span class="lang on" data-l="ja">日本語</span>
    <span class="lang" data-l="en">English</span>
    <span class="lang" data-l="ko">한국어</span>
    <span class="lang" data-l="zh">中文</span>
  </div>
  <p class="label">説明のレベル</p>
  <div class="seg" id="levels">
    <button class="on" data-v="beginner">はじめて</button>
    <button data-v="pro">くわしい</button>
  </div>
  <p class="label">質問</p>
  <textarea id="q" placeholder="例：分散投資ってなに？　なぜ大事なの？"></textarea>
  <button class="ask" id="askBtn">聞いてみる</button>
  <div class="answer" id="answer"></div>
  <div class="foot">
    arbitrage のAIアナリストは、プロが使う分析の作法で中立に読み解くAIです。AIによる情報提供であり、利益を保証するものではありません。投資の判断はご自身の責任で行ってください。
  </div>
</div>
<script>
  let lang = "ja";
  let level = "beginner";
  document.getElementById("langs").addEventListener("click", function(e){
    const b = e.target.closest(".lang"); if(!b) return;
    lang = b.dataset.l;
    document.querySelectorAll("#langs .lang").forEach(x => x.classList.toggle("on", x === b));
  });
  document.getElementById("levels").addEventListener("click", function(e){
    const b = e.target.closest("button"); if(!b) return;
    level = b.dataset.v;
    document.querySelectorAll("#levels button").forEach(x => x.classList.toggle("on", x === b));
  });
  const btn = document.getElementById("askBtn");
  const ans = document.getElementById("answer");
  async function ask(){
    const q = document.getElementById("q").value.trim();
    if(!q){ return; }
    btn.disabled = true;
    btn.textContent = "考えています…";
    ans.classList.add("show");
    ans.innerHTML = '<span class="thinking">アナリストが考えています…</span>';
    try{
      const r = await fetch("/ask", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body: JSON.stringify({question:q, lang:lang, level:level})
      });
      const data = await r.json();
      if(data.error){ ans.textContent = "うまくいきませんでした：" + data.error; }
      else { ans.textContent = data.answer; }
    }catch(err){
      ans.textContent = "通信でエラーが起きました。少し待ってもう一度試してください。";
    }
    btn.disabled = false;
    btn.textContent = "聞いてみる";
  }
  btn.addEventListener("click", ask);
</script>
</body>
</html>
"""

RENSHUJO_HTML = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>arbitrage — 投資の練習場</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  :root{
    --ink:#16202e; --paper:#faf8f3; --surface:#ffffff;
    --jade:#0f7a5f; --jade-soft:#e3f1ec; --amber:#b5751a; --amber-soft:#f6ecdb;
    --muted:#5d6470; --border:#e7e2d7; --border-strong:#d8d2c4;
  }
  *{box-sizing:border-box}
  body{margin:0; background:var(--paper); color:var(--ink); line-height:1.7;
    font-family:'Noto Sans JP', system-ui, 'Hiragino Sans','Yu Gothic','Malgun Gothic','Microsoft YaHei', sans-serif; -webkit-font-smoothing:antialiased}
  .wrap{max-width:760px; margin:0 auto; padding:24px 18px 60px}
  .back{display:inline-block; font-size:13px; color:var(--muted); text-decoration:none; margin-bottom:18px}
  .back:hover{color:var(--jade)}
  .brand{font-size:18px; color:var(--muted); margin:0 0 2px}
  .hero{font-size:26px; font-weight:700; margin:0 0 6px}
  .lead{font-size:14px; color:var(--muted); margin:0 0 26px}
  .grid{display:grid; grid-template-columns:repeat(auto-fit, minmax(220px,1fr)); gap:14px}
  .card{background:var(--surface); border:1px solid var(--border); border-radius:16px; padding:20px; display:flex; flex-direction:column; text-decoration:none; color:inherit}
  .card .badge{align-self:flex-start; font-size:11px; font-weight:500; padding:3px 9px; border-radius:999px; margin-bottom:12px; color:var(--jade); background:var(--jade-soft)}
  .card h3{font-size:17px; font-weight:500; margin:0 0 6px}
  .card p{font-size:13px; color:var(--muted); margin:0 0 16px; flex:1}
  .card .act{font-size:14px; font-weight:500; color:var(--jade)}
  a.card:hover{border-color:var(--jade)}
  .foot{margin-top:30px; border-top:1px solid var(--border); padding-top:16px; font-size:12px; color:var(--muted)}
</style>
</head>
<body>
<div class="wrap">
  <a class="back" href="/">← arbitrage トップへ</a>
  <p class="brand">arbitrage</p>
  <h1 class="hero">投資の練習場</h1>
  <p class="lead">すべて架空のお金です。本物のお金は使いません。安全に、投資のやり方を体験しましょう。</p>
  <div class="grid">
    <a class="card" href="/basics">
      <span class="badge">使えます</span>
      <h3>コツコツ積立で比べる</h3>
      <p>「ひとつに集中」と「分散・長期・積立」を比べ、揺れの違いを体験します。</p>
      <span class="act">開く →</span>
    </a>
    <a class="card" href="/factor">
      <span class="badge">使えます</span>
      <h3>ファクター投資</h3>
      <p>割安・上昇中・質が高い、などの特徴で会社をふるい分けて投資します。</p>
      <span class="act">開く →</span>
    </a>
    <a class="card" href="/arbitrage">
      <span class="badge">使えます</span>
      <h3>アービトラージ</h3>
      <p>「小さく勝ち続けるが、関係が壊れると暴落する」正体を体験します。</p>
      <span class="act">開く →</span>
    </a>
  </div>
  <div class="foot">これらは教育・練習目的の仮想シミュレーションです。会社・値動き・お金はすべて架空で、将来の成績を示すものではありません。</div>
</div>
</body>
</html>
"""

KIHON_HTML = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>arbitrage — 練習投資シミュレーター</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root{
    --ink:#16202e; --paper:#faf8f3; --surface:#ffffff;
    --jade:#0f7a5f; --jade-soft:#e3f1ec; --amber:#b5751a; --amber-soft:#f6ecdb;
    --muted:#5d6470; --border:#e7e2d7; --border-strong:#d8d2c4; --loss:#b23b3b;
  }
  *{box-sizing:border-box}
  body{margin:0; background:var(--paper); color:var(--ink); line-height:1.7;
    font-family:'Noto Sans JP', system-ui, 'Hiragino Sans', 'Yu Gothic', sans-serif; -webkit-font-smoothing:antialiased}
  .wrap{max-width:720px; margin:0 auto; padding:20px 18px 60px}
  .topbar{display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; margin-bottom:22px}
  .brand{font-size:22px; font-weight:700; letter-spacing:.5px}
  .badge{font-size:12px; font-weight:500; color:var(--amber); background:var(--amber-soft); padding:5px 11px; border-radius:999px}
  .hero{font-size:24px; font-weight:700; margin:0 0 6px}
  .lead{font-size:14px; color:var(--muted); margin:0 0 22px}
  .card{background:var(--surface); border:1px solid var(--border); border-radius:16px; padding:20px; margin-bottom:18px}
  .row{display:flex; align-items:center; gap:14px; margin-bottom:16px}
  .row label{font-size:14px; min-width:96px; color:var(--muted)}
  .row input[type=range]{flex:1; accent-color:var(--jade)}
  .row .val{font-size:15px; font-weight:500; min-width:92px; text-align:right}
  .run{width:100%; font-family:inherit; font-size:16px; font-weight:500; padding:13px; border:0; border-radius:10px;
    background:var(--ink); color:#fff; cursor:pointer}
  .stats{display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-bottom:18px}
  .stat{background:var(--paper); border:1px solid var(--border); border-radius:12px; padding:12px}
  .stat .k{font-size:12px; color:var(--muted); margin-bottom:4px}
  .stat .v{font-size:20px; font-weight:700}
  .legend{display:flex; gap:18px; font-size:13px; margin:0 0 8px}
  .legend span{display:flex; align-items:center; gap:7px; color:var(--muted)}
  .swatch{width:14px; height:3px; border-radius:2px; display:inline-block}
  .chartbox{position:relative; height:280px}
  .note{font-size:13px; color:var(--muted); background:var(--jade-soft); border-radius:12px; padding:12px 14px; margin-top:16px}
  .foot{margin-top:22px; display:flex; gap:8px; font-size:12px; color:var(--muted); border-top:1px solid var(--border); padding-top:14px}
</style>
</head>
<body>
<div class="wrap">
  <p style="margin:0 0 14px"><a href="/practice" style="font-size:13px;color:#0f7a5f;text-decoration:none">← 練習場へ</a></p>

  <div class="topbar">
    <span class="brand">arbitrage</span>
    <span class="badge">練習モード・仮想のお金</span>
  </div>

  <h1 class="hero">アナリストの仕事場 — 練習投資シミュレーター</h1>
  <p class="lead">仮想のお金で投資を動かして、結果を見てみましょう。本物のお金は一切使いません。</p>

  <div class="card">
    <div class="row">
      <label>期間</label>
      <input type="range" id="years" min="1" max="30" step="1" value="10">
      <span class="val" id="yearsVal">10 年</span>
    </div>
    <div class="row">
      <label>毎月の積立</label>
      <input type="range" id="monthly" min="5000" max="50000" step="5000" value="10000">
      <span class="val" id="monthlyVal">¥10,000</span>
    </div>
    <button class="run" id="runBtn">この内容で投資してみる</button>
  </div>

  <div class="stats">
    <div class="stat"><div class="k">投資した合計</div><div class="v" id="invested">—</div></div>
    <div class="stat"><div class="k">集中投資の結果</div><div class="v" id="conc">—</div></div>
    <div class="stat"><div class="k">分散・長期・積立の結果</div><div class="v" id="div">—</div></div>
  </div>

  <div class="card">
    <div class="legend">
      <span><i class="swatch" style="background:var(--amber)"></i>ひとつに集中投資</span>
      <span><i class="swatch" style="background:var(--jade)"></i>分散・長期・積立</span>
      <span><i class="swatch" style="background:var(--muted)"></i>投資した元本</span>
    </div>
    <div class="chartbox"><canvas id="chart"></canvas></div>
    <div class="note" id="insight"></div>
  </div>

  <div class="foot">
    <span>これは教育・練習目的の仮想シミュレーションです。実際の値動きとは異なり、将来の成績を示すものではありません。投資の判断はご自身の責任で。</span>
  </div>

</div>

<script>
  const $ = id => document.getElementById(id);
  const yen = n => '¥' + Math.round(n).toLocaleString('ja-JP');

  function randn(){
    let u=0, v=0;
    while(u===0) u=Math.random();
    while(v===0) v=Math.random();
    return Math.sqrt(-2*Math.log(u)) * Math.cos(2 * Math.PI * v);
  }

  function simulate(months, monthly, mean, sd){
    let bal = 0;
    const out = [];
    for(let m=0; m<months; m++){
      bal += monthly;
      bal = bal * (1 + mean + sd * randn());
      if(bal < 0) bal = 0;
      out.push(bal);
    }
    return out;
  }

  let chart;

  function run(){
    const years = +$('years').value;
    const monthly = +$('monthly').value;
    const months = years * 12;
    const invested = monthly * months;

    const concentrated = simulate(months, monthly, 0.007, 0.080);
    const diversified  = simulate(months, monthly, 0.0055, 0.025);

    const labels = [];
    for(let m=0; m<months; m++) labels.push(m%12===11 ? ((m+1)/12)+'年' : '');

    const investedLine = [];
    for(let m=0; m<months; m++) investedLine.push(monthly*(m+1));

    const concFinal = concentrated[months-1];
    const divFinal  = diversified[months-1];

    $('invested').textContent = yen(invested);
    $('conc').textContent = yen(concFinal);
    $('conc').style.color = concFinal >= invested ? 'var(--jade)' : 'var(--loss)';
    $('div').textContent = yen(divFinal);
    $('div').style.color = divFinal >= invested ? 'var(--jade)' : 'var(--loss)';

    const ds = [
      {label:'集中', data:concentrated, borderColor:'#b5751a', borderWidth:2, pointRadius:0, tension:0.1},
      {label:'分散', data:diversified, borderColor:'#0f7a5f', borderWidth:2, pointRadius:0, tension:0.1},
      {label:'元本', data:investedLine, borderColor:'#5d6470', borderWidth:1.5, borderDash:[5,5], pointRadius:0, tension:0}
    ];

    if(chart){
      chart.data.labels = labels;
      chart.data.datasets = ds;
      chart.update();
    } else {
      chart = new Chart($('chart').getContext('2d'), {
        type:'line',
        data:{labels, datasets:ds},
        options:{
          responsive:true, maintainAspectRatio:false,
          plugins:{legend:{display:false}, tooltip:{callbacks:{label:c=>yen(c.parsed.y)}}},
          scales:{
            x:{grid:{display:false}, ticks:{maxRotation:0, autoSkip:false, font:{family:'Noto Sans JP'}}},
            y:{ticks:{callback:v=>'¥'+(v/10000).toFixed(0)+'万', font:{family:'Noto Sans JP'}}, grid:{color:'#eee'}}
          }
        }
      });
    }

    const winC = concFinal >= invested, winD = divFinal >= invested;
    let line = `今回は、集中投資が ${yen(concFinal)}、分散・長期・積立が ${yen(divFinal)}(投資した合計は ${yen(invested)})。`;
    line += 'もう一度押すと結果は変わります。これが「絶対はない」ということ。';
    line += 'でも、緑(分散・長期・積立)の線のほうが上下の揺れが小さいのが見えますか?この揺れの小ささが、大きなマイナスを防ぐ「努力」です。';
    $('insight').textContent = line;
    $('runBtn').textContent = 'もう一度やってみる';
  }

  $('years').addEventListener('input', e => $('yearsVal').textContent = e.target.value + ' 年');
  $('monthly').addEventListener('input', e => $('monthlyVal').textContent = yen(+e.target.value));
  $('runBtn').addEventListener('click', run);

  window.addEventListener('load', run);
</script>
</body>
</html>
"""

FACTOR_HTML = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>arbitrage — ファクター投資の練習</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root{
    --ink:#16202e; --paper:#faf8f3; --surface:#ffffff;
    --jade:#0f7a5f; --jade-soft:#e3f1ec; --amber:#b5751a; --amber-soft:#f6ecdb;
    --muted:#5d6470; --border:#e7e2d7; --border-strong:#d8d2c4; --loss:#b23b3b;
  }
  *{box-sizing:border-box}
  body{margin:0; background:var(--paper); color:var(--ink); line-height:1.7;
    font-family:'Noto Sans JP', system-ui, 'Hiragino Sans', 'Yu Gothic', sans-serif; -webkit-font-smoothing:antialiased}
  .wrap{max-width:720px; margin:0 auto; padding:20px 18px 60px}
  .topbar{display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; margin-bottom:22px}
  .brand{font-size:22px; font-weight:700; letter-spacing:.5px}
  .badge{font-size:12px; font-weight:500; color:var(--amber); background:var(--amber-soft); padding:5px 11px; border-radius:999px}
  .hero{font-size:24px; font-weight:700; margin:0 0 6px}
  .lead{font-size:14px; color:var(--muted); margin:0 0 22px}
  .card{background:var(--surface); border:1px solid var(--border); border-radius:16px; padding:20px; margin-bottom:18px}
  .label{font-size:13px; color:var(--muted); margin:0 0 8px; font-weight:500}
  .seg{display:flex; flex-wrap:wrap; gap:8px; margin-bottom:18px}
  .seg button{font-family:inherit; font-size:14px; padding:9px 16px; border:1px solid var(--border-strong); border-radius:10px;
    background:var(--surface); color:var(--muted); cursor:pointer}
  .seg button.on{background:var(--jade); color:#fff; border-color:var(--jade); font-weight:500}
  .row{display:flex; align-items:center; gap:14px; margin-bottom:16px}
  .row label{font-size:14px; min-width:60px; color:var(--muted)}
  .row input[type=range]{flex:1; accent-color:var(--jade)}
  .row .val{font-size:15px; font-weight:500; min-width:64px; text-align:right}
  .run{width:100%; font-family:inherit; font-size:16px; font-weight:500; padding:13px; border:0; border-radius:10px;
    background:var(--ink); color:#fff; cursor:pointer}
  .stats{display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-bottom:18px}
  .stat{background:var(--paper); border:1px solid var(--border); border-radius:12px; padding:12px}
  .stat .k{font-size:12px; color:var(--muted); margin-bottom:4px}
  .stat .v{font-size:19px; font-weight:700}
  .legend{display:flex; gap:18px; font-size:13px; margin:0 0 8px; flex-wrap:wrap}
  .legend span{display:flex; align-items:center; gap:7px; color:var(--muted)}
  .swatch{width:14px; height:3px; border-radius:2px; display:inline-block}
  .chartbox{position:relative; height:270px}
  .picks{display:flex; flex-wrap:wrap; gap:8px; margin-top:4px}
  .pick{font-size:13px; background:var(--jade-soft); color:var(--jade); padding:6px 11px; border-radius:999px}
  .pick b{font-weight:700}
  .note{font-size:13px; color:var(--muted); background:var(--jade-soft); border-radius:12px; padding:12px 14px; margin-top:16px}
  .foot{margin-top:22px; display:flex; gap:8px; font-size:12px; color:var(--muted); border-top:1px solid var(--border); padding-top:14px}
  h3{font-size:15px; font-weight:500; margin:0 0 10px}
</style>
</head>
<body>
<div class="wrap">
  <p style="margin:0 0 14px"><a href="/practice" style="font-size:13px;color:#0f7a5f;text-decoration:none">← 練習場へ</a></p>

  <div class="topbar">
    <span class="brand">arbitrage</span>
    <span class="badge">練習モード・架空の100万円</span>
  </div>

  <h1 class="hero">ファクター投資の練習</h1>
  <p class="lead">特徴(ファクター)で会社をふるい分けて投資します。会社はすべて架空、お金も架空の100万円です。</p>

  <div class="card">
    <p class="label">どの特徴で会社を選ぶ?</p>
    <div class="seg" id="seg">
      <button class="on" data-f="value">割安な会社</button>
      <button data-f="momentum">上昇中の会社</button>
      <button data-f="quality">質が高い会社</button>
    </div>
    <div class="row">
      <label>期間</label>
      <input type="range" id="years" min="1" max="20" step="1" value="5">
      <span class="val" id="yearsVal">5 年</span>
    </div>
    <button class="run" id="runBtn">この特徴で投資してみる</button>
  </div>

  <div class="stats">
    <div class="stat"><div class="k">この戦略の結果</div><div class="v" id="strat">—</div></div>
    <div class="stat"><div class="k">市場全体の結果</div><div class="v" id="market">—</div></div>
    <div class="stat"><div class="k">一番きつかった下落</div><div class="v" id="dd">—</div></div>
  </div>

  <div class="card">
    <div class="legend">
      <span><i class="swatch" style="background:var(--jade)"></i>選んだ戦略</span>
      <span><i class="swatch" style="background:var(--amber)"></i>市場全体(全部持つ)</span>
    </div>
    <div class="chartbox"><canvas id="chart"></canvas></div>
    <div class="note" id="insight"></div>
  </div>

  <div class="card">
    <h3>選ばれた会社(特徴スコアの高い上位5社)</h3>
    <div class="picks" id="picks"></div>
  </div>

  <div class="foot">
    <span>これは教育・練習目的の仮想シミュレーションです。会社・株価・お金はすべて架空で、実在の銘柄や将来の成績を示すものではありません。</span>
  </div>

</div>

<script>
  const $ = id => document.getElementById(id);
  const yen = n => '¥' + Math.round(n).toLocaleString('ja-JP');
  const START = 1000000;

  const NAMES = ['アオゾラ電機','ヒカリ製薬','みどり物産','そら運輸','ほし食品','かぜ通信',
                 'やま建設','うみ商事','つき自動車','もり化学','かわ銀行','のぞみ電力'];
  const FNAME = {value:'割安', momentum:'上昇中', quality:'質が高い'};

  function randn(){
    let u=0,v=0;
    while(u===0)u=Math.random();
    while(v===0)v=Math.random();
    return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v);
  }

  let chart;
  let factor = 'value';

  function run(){
    const years = +$('years').value;
    const months = years*12;

    const universe = NAMES.map(name => ({name, score: Math.round(Math.random()*100)}));
    const sorted = [...universe].sort((a,b)=>b.score-a.score);
    const picks = sorted.slice(0,5);
    const pickSet = new Set(picks.map(p=>p.name));

    let stratBal = START, marketBal = START;
    const stratLine = [], marketLine = [];
    let peak = START, maxDD = 0;

    for(let m=0; m<months; m++){
      const marketR = 0.005 + 0.04*randn();
      const factorPremium = 0.003 + 0.015*randn();
      let stratSum = 0, marketSum = 0;
      universe.forEach(s => {
        const tilt = factorPremium * ((s.score-50)/50);
        const r = marketR + tilt + 0.03*randn();
        marketSum += r;
        if(pickSet.has(s.name)) stratSum += r;
      });
      const marketR_avg = marketSum / universe.length;
      const stratR_avg = stratSum / picks.length;

      marketBal *= (1 + marketR_avg); if(marketBal<0) marketBal=0;
      stratBal  *= (1 + stratR_avg);  if(stratBal<0) stratBal=0;

      if(stratBal > peak) peak = stratBal;
      const dd = (peak - stratBal)/peak;
      if(dd > maxDD) maxDD = dd;

      stratLine.push(stratBal);
      marketLine.push(marketBal);
    }

    const stratFinal = stratLine[months-1];
    const marketFinal = marketLine[months-1];

    $('strat').textContent = yen(stratFinal);
    $('strat').style.color = stratFinal >= START ? 'var(--jade)' : 'var(--loss)';
    $('market').textContent = yen(marketFinal);
    $('market').style.color = marketFinal >= START ? 'var(--jade)' : 'var(--loss)';
    $('dd').textContent = '-' + (maxDD*100).toFixed(0) + '%';
    $('dd').style.color = 'var(--loss)';

    $('picks').innerHTML = picks.map(p =>
      `<span class="pick">${p.name} <b>${p.score}</b></span>`).join('');

    const labels = [];
    for(let m=0; m<months; m++) labels.push(m%12===11 ? ((m+1)/12)+'年' : '');

    const ds = [
      {label:'戦略', data:stratLine, borderColor:'#0f7a5f', borderWidth:2, pointRadius:0, tension:0.1},
      {label:'市場', data:marketLine, borderColor:'#b5751a', borderWidth:2, pointRadius:0, tension:0.1}
    ];

    if(chart){
      chart.data.labels = labels;
      chart.data.datasets = ds;
      chart.update();
    } else {
      chart = new Chart($('chart').getContext('2d'), {
        type:'line',
        data:{labels, datasets:ds},
        options:{
          responsive:true, maintainAspectRatio:false,
          plugins:{legend:{display:false}, tooltip:{callbacks:{label:c=>yen(c.parsed.y)}}},
          scales:{
            x:{grid:{display:false}, ticks:{maxRotation:0, autoSkip:false, font:{family:'Noto Sans JP'}}},
            y:{ticks:{callback:v=>(v/10000).toFixed(0)+'万', font:{family:'Noto Sans JP'}}, grid:{color:'#eee'}}
          }
        }
      });
    }

    const beat = stratFinal > marketFinal;
    let t = `今回、「${FNAME[factor]}な会社」を選んだ戦略は ${yen(stratFinal)}、市場全体(全部持つ)は ${yen(marketFinal)}。`;
    t += beat ? 'この戦略が市場に勝ちました。' : '今回は市場全体のほうが上でした。';
    t += `途中で一番きつかったときは、最高値から ${(maxDD*100).toFixed(0)}% 下がっています。`;
    t += '「もう一度」を押すと結果は変わります——ファクターは\"いつも勝てる\"わけではなく、勝つ年も負ける年もあるのが現実。だから本物のプロは複数の特徴を組み合わせて、外れたときの痛手を小さくします。';
    $('insight').textContent = t;
    $('runBtn').textContent = 'もう一度やってみる';
  }

  $('seg').addEventListener('click', e => {
    const b = e.target.closest('button'); if(!b) return;
    factor = b.dataset.f;
    document.querySelectorAll('#seg button').forEach(x=>x.classList.toggle('on', x===b));
    run();
  });
  $('years').addEventListener('input', e => $('yearsVal').textContent = e.target.value + ' 年');
  $('runBtn').addEventListener('click', run);
  window.addEventListener('load', run);
</script>
</body>
</html>
"""

ARBITRAGE_HTML = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>arbitrage — アービトラージの練習</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root{
    --ink:#16202e; --paper:#faf8f3; --surface:#ffffff;
    --jade:#0f7a5f; --jade-soft:#e3f1ec; --amber:#b5751a; --amber-soft:#f6ecdb;
    --muted:#5d6470; --border:#e7e2d7; --border-strong:#d8d2c4; --loss:#b23b3b; --loss-soft:#f6e3e1;
  }
  *{box-sizing:border-box}
  body{margin:0; background:var(--paper); color:var(--ink); line-height:1.7;
    font-family:'Noto Sans JP', system-ui, 'Hiragino Sans', 'Yu Gothic', sans-serif; -webkit-font-smoothing:antialiased}
  .wrap{max-width:720px; margin:0 auto; padding:20px 18px 60px}
  .topbar{display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; margin-bottom:22px}
  .brand{font-size:22px; font-weight:700; letter-spacing:.5px}
  .badge{font-size:12px; font-weight:500; color:var(--amber); background:var(--amber-soft); padding:5px 11px; border-radius:999px}
  .hero{font-size:24px; font-weight:700; margin:0 0 6px}
  .lead{font-size:14px; color:var(--muted); margin:0 0 22px}
  .card{background:var(--surface); border:1px solid var(--border); border-radius:16px; padding:20px; margin-bottom:18px}
  .label{font-size:13px; color:var(--muted); margin:0 0 8px; font-weight:500}
  .seg{display:flex; gap:8px; margin-bottom:18px}
  .seg button{font-family:inherit; font-size:14px; padding:9px 16px; border:1px solid var(--border-strong); border-radius:10px;
    background:var(--surface); color:var(--muted); cursor:pointer}
  .seg button.on{background:var(--jade); color:#fff; border-color:var(--jade); font-weight:500}
  .row{display:flex; align-items:center; gap:14px; margin-bottom:16px}
  .row label{font-size:14px; min-width:60px; color:var(--muted)}
  .row input[type=range]{flex:1; accent-color:var(--jade)}
  .row .val{font-size:15px; font-weight:500; min-width:64px; text-align:right}
  .run{width:100%; font-family:inherit; font-size:16px; font-weight:500; padding:13px; border:0; border-radius:10px;
    background:var(--ink); color:#fff; cursor:pointer}
  .stats{display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-bottom:18px}
  .stat{background:var(--paper); border:1px solid var(--border); border-radius:12px; padding:12px}
  .stat .k{font-size:12px; color:var(--muted); margin-bottom:4px}
  .stat .v{font-size:19px; font-weight:700}
  .chartbox{position:relative; height:270px}
  .note{font-size:13px; color:var(--muted); background:var(--loss-soft); border-radius:12px; padding:12px 14px; margin-top:16px}
  .foot{margin-top:22px; display:flex; gap:8px; font-size:12px; color:var(--muted); border-top:1px solid var(--border); padding-top:14px}
</style>
</head>
<body>
<div class="wrap">
  <p style="margin:0 0 14px"><a href="/practice" style="font-size:13px;color:#0f7a5f;text-decoration:none">← 練習場へ</a></p>

  <div class="topbar">
    <span class="brand">arbitrage</span>
    <span class="badge">練習モード・架空の100万円</span>
  </div>

  <h1 class="hero">アービトラージの練習(ペアトレード)</h1>
  <p class="lead">いつも一緒に動く架空の2社「ソラ航空」と「ソラ観光」。値段の差が開いたら「また戻る」に賭ける戦略です。お金も会社も架空です。</p>

  <div class="card">
    <p class="label">賭けの大きさ</p>
    <div class="seg" id="seg">
      <button class="on" data-m="calm">控えめ</button>
      <button data-m="bold">強気</button>
    </div>
    <div class="row">
      <label>期間</label>
      <input type="range" id="years" min="1" max="15" step="1" value="5">
      <span class="val" id="yearsVal">5 年</span>
    </div>
    <button class="run" id="runBtn">この設定でやってみる</button>
  </div>

  <div class="stats">
    <div class="stat"><div class="k">最終残高</div><div class="v" id="bal">—</div></div>
    <div class="stat"><div class="k">関係が壊れた回数</div><div class="v" id="crash">—</div></div>
    <div class="stat"><div class="k">一番きつかった下落</div><div class="v" id="dd">—</div></div>
  </div>

  <div class="card">
    <div class="chartbox"><canvas id="chart"></canvas></div>
    <div class="note" id="insight"></div>
  </div>

  <div class="foot">
    <span>これは教育・練習目的の仮想シミュレーションです。会社・値動き・お金はすべて架空で、実在の銘柄や将来の成績を示すものではありません。</span>
  </div>

</div>

<script>
  const $ = id => document.getElementById(id);
  const yen = n => '¥' + Math.round(n).toLocaleString('ja-JP');
  const START = 1000000;

  function randn(){
    let u=0,v=0;
    while(u===0)u=Math.random();
    while(v===0)v=Math.random();
    return Math.sqrt(-2*Math.log(u))*Math.cos(2*Math.PI*v);
  }

  const PARAMS = {
    calm: {base:0.0018, noise:0.004, crashProb:0.010, crashMin:0.05, crashMax:0.13},
    bold: {base:0.0042, noise:0.008, crashProb:0.016, crashMin:0.15, crashMax:0.32}
  };

  let chart;
  let mode = 'calm';

  function run(){
    const years = +$('years').value;
    const steps = years*52;
    const p = PARAMS[mode];

    let bal = START, peak = START, maxDD = 0, crashes = 0;
    const line = [];
    for(let i=0; i<steps; i++){
      let r;
      if(Math.random() < p.crashProb){
        r = -(p.crashMin + Math.random()*(p.crashMax - p.crashMin));
        crashes++;
      } else {
        r = p.base + p.noise*randn();
      }
      bal *= (1 + r);
      if(bal < 0) bal = 0;
      if(bal > peak) peak = bal;
      const dd = (peak - bal)/peak;
      if(dd > maxDD) maxDD = dd;
      line.push(bal);
    }
    const final = line[steps-1];

    $('bal').textContent = yen(final);
    $('bal').style.color = final >= START ? 'var(--jade)' : 'var(--loss)';
    $('crash').textContent = crashes + ' 回';
    $('crash').style.color = 'var(--loss)';
    $('dd').textContent = '-' + (maxDD*100).toFixed(0) + '%';
    $('dd').style.color = 'var(--loss)';

    const labels = [];
    for(let i=0; i<steps; i++) labels.push((i%52===51) ? ((i+1)/52)+'年' : '');

    const ds = [{label:'残高', data:line, borderColor:'#0f7a5f', borderWidth:2, pointRadius:0, tension:0.05}];
    if(chart){
      chart.data.labels = labels; chart.data.datasets = ds; chart.update();
    } else {
      chart = new Chart($('chart').getContext('2d'), {
        type:'line', data:{labels, datasets:ds},
        options:{
          responsive:true, maintainAspectRatio:false,
          plugins:{legend:{display:false}, tooltip:{callbacks:{label:c=>yen(c.parsed.y)}}},
          scales:{
            x:{grid:{display:false}, ticks:{maxRotation:0, autoSkip:false, font:{family:'Noto Sans JP'}}},
            y:{ticks:{callback:v=>(v/10000).toFixed(0)+'万', font:{family:'Noto Sans JP'}}, grid:{color:'#eee'}}
          }
        }
      });
    }

    let t = `今回は ${crashes} 回、2社の関係が壊れました。最終残高は ${yen(final)}、一番きつい下落は ${(maxDD*100).toFixed(0)}%。`;
    t += '線をよく見て。最初はスルスル増えますよね?小さな"成功"(ペニー)をたくさん拾うからです。';
    t += 'でも、2社の関係が壊れると一気にドカンと落ちる。これがアービトラージの正体——「走ってくるトラックの前で小銭を拾う」とよく言われます。';
    t += '小さく勝ち続けても、一回の暴落で何ヶ月分も吹き飛ぶ。「リスクなしで儲かる」は幻想で、世界の天才ファンドさえ、これで破綻しました。「もう一度」で結果は変わります。';
    $('insight').textContent = t;
    $('runBtn').textContent = 'もう一度やってみる';
  }

  $('seg').addEventListener('click', e => {
    const b = e.target.closest('button'); if(!b) return;
    mode = b.dataset.m;
    document.querySelectorAll('#seg button').forEach(x=>x.classList.toggle('on', x===b));
    run();
  });
  $('years').addEventListener('input', e => $('yearsVal').textContent = e.target.value + ' 年');
  $('runBtn').addEventListener('click', run);
  window.addEventListener('load', run);
</script>
</body>
</html>
"""


SHAIN_HTML = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>arbitrage — 社員紹介室</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root{--ink:#16202e;--paper:#faf8f3;--surface:#ffffff;--jade:#0f7a5f;--jade-soft:#e3f1ec;--amber:#b5751a;--amber-soft:#f6ecdb;--muted:#5d6470;--border:#e7e2d7;--border-strong:#d8d2c4;}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);line-height:1.7;font-family:'Noto Sans JP',system-ui,'Hiragino Sans','Yu Gothic',sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:820px;margin:0 auto;padding:24px 18px 60px}
.topbar{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:20px}
.brand{font-size:22px;font-weight:700;letter-spacing:.5px}
.badge{font-size:12px;font-weight:500;color:var(--jade);background:var(--jade-soft);padding:5px 11px;border-radius:999px}
.hero{font-size:24px;font-weight:700;margin:0 0 6px}
.lead{font-size:14px;color:var(--muted);margin:0 0 22px}
.members{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.member{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:15px 16px}
.mhead{display:flex;align-items:center;gap:9px;margin-bottom:7px}
.me{font-size:22px}
.mn{font-weight:700;font-size:15px}
.mr{font-size:13px;color:var(--muted);margin:0 0 10px}
.mp{font-size:12.5px;margin:0;color:var(--ink);background:var(--amber-soft);border-radius:10px;padding:8px 10px}
.ptag{display:inline-block;font-size:11px;font-weight:700;color:var(--amber);margin-right:7px}
.note{grid-column:1 / -1;background:var(--jade-soft);border:1px solid #cfe5dd;border-radius:14px;padding:14px 16px;font-size:13px;color:var(--muted);margin-top:4px}
.foot{margin-top:24px;border-top:1px solid var(--border);padding-top:14px;font-size:12px;color:var(--muted)}
@media(max-width:560px){.members{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="wrap">
<p style="margin:0 0 14px"><a href="/" style="font-size:13px;color:#0f7a5f;text-decoration:none">← arbitrage トップへ</a></p>
<div class="topbar"><span class="brand">arbitrage</span><span class="badge">社員紹介室</span></div>
<h1 class="hero">うちの社員たち</h1>
<p class="lead">「負けない会社」をつくるために集めた仲間です。一人ひとりが、破ってはいけない約束のどれかを担当しています。スター選手はいません。でも、みんなで支え合います。</p>
<a href="/meeting-room" style="display:inline-block;text-decoration:none;background:#0f7a5f;color:#fff;font-weight:500;font-size:14px;padding:11px 18px;border-radius:10px;margin:0 0 18px">🗣️ この人たちで会議してもらう →</a>
<div class="members">
<div class="member"><div class="mhead"><span class="me">🔎</span><span class="mn">事実確認係ハジメ</span></div><p class="md">各取引所から渡された実データ（今の価格・気配・出来高感・直近の値動き）を正しく読み、どの数字をどう見るかを実演する。思い込みは足さない。</p><p class="mp"><span class="ptag">守る約束</span> ②③ 出どころ・鮮度・一情報源を警告し、最新値は持たないと正直に言い、確認は本人に促す</p></div>
<div class="member"><div class="mhead"><span class="me">⚖️</span><span class="mn">価格差ウォッチャー サヤミ</span></div><p class="md">同じ先物が取引所Aと取引所Bでいくら違うか（価格差・乖離）を見て、差が開いているか・縮みそうかを評価する。狙うのは上下当てではなく取引所間の歪み。</p><p class="mp"><span class="ptag">守る約束</span> ①④ 『見かけの価格差』はコストで消えやすいので、差があるだけでは“いい”と言わない</p></div>
<div class="member"><div class="mhead"><span class="me">🧮</span><span class="mn">コスト精査役 テスリ</span></div><p class="md">両側の取引手数料＋送金料＋税を全部引いて、それでも『手取りで残る差』になる時だけを“いい”とする。利幅は薄い前提で語る。</p><p class="mp"><span class="ptag">守る約束</span> ①② 見かけの差ではなく手取りの差で語り、コストでサヤが消える落とし穴を必ず示す</p></div>
<div class="member"><div class="mhead"><span class="me">🚚</span><span class="mn">送金・約定リスク係 オクリ</span></div><p class="md">送金時間・出金停止リスク・約定スピード／スリッページ・取引所の信用リスクを点検する。速く正確に両側を執行できない時は『今はよくない』と見送る。</p><p class="mp"><span class="ptag">守る約束</span> ④③ サヤがある間に実際に動かせるかを現実目線で問い、無理なら見送る</p></div>
<div class="member"><div class="mhead"><span class="me">⚠️</span><span class="mn">清算・レバレッジ係 セイサン</span></div><p class="md">先物特有のレバレッジ清算・必要証拠金・（パーペチュアルなら）ファンディングの影響を点検する。無理なレバや証拠金不足で清算される危険を止める。</p><p class="mp"><span class="ptag">守る約束</span> ①④ レバは控えめに。サヤを取る前に清算される危険には強くブレーキをかける</p></div>
<div class="member"><div class="mhead"><span class="me">📦</span><span class="mn">資金分散係 ブンサン</span></div><p class="md">資金を1取引所に集中させない、出金詰まり・取引所トラブルに備えて分散できているかを見る。一つの取引所に依存した計画には釘を刺す。</p><p class="mp"><span class="ptag">守る約束</span> ④ 一つに頼り切る計画を戒め、分散と備えを促す</p></div>
<div class="member"><div class="mhead"><span class="me">📜</span><span class="mn">歴史係コヨミ</span></div><p class="md">過去にサヤ取りがうまくいかなかった例（取引所破綻・出金停止・急な価格差消失）を思い出させ、楽観に冷や水をかける。前提が違えば結論も変わると伝える。</p><p class="mp"><span class="ptag">守る約束</span> ①④ 過去の実例で「絶対はない」を示し、前提が違えば結論も違うと確認する</p></div>
<div class="member"><div class="mhead"><span class="me">😈</span><span class="mn">悪魔の代弁者アマノジャク</span></div><p class="md">わざと反対の立場で、見落とされたリスクや「うまくいかない場合」を指摘する。楽観が過ぎれば強く水を差し、断定や暴走にブレーキをかける。</p><p class="mp"><span class="ptag">守る約束</span> ① 「絶対」という考え方そのものを疑い、言わせない</p></div>
<div class="member"><div class="mhead"><span class="me">🔍</span><span class="mn">監査役カンサ</span></div><p class="md">全員の意見にあやしい点・言い過ぎ・抜けがないかを最後に点検する。ルール違反（断定・個別売買の指示）があれば指摘し、最終判断は本人に委ねる。</p><p class="mp"><span class="ptag">守る約束</span> ②④ あやしい点を遠慮なく指摘し、最終判断は本人に委ねる</p></div>
<div class="note">この人たちがいても「絶対にうまくいく」とは言えません。それでも、誰が何に責任を持つかがはっきりしていると、まちがいに早く気づけます。それが、このチームをそろえる理由です。</div>
</div>
<div class="foot">arbitrage は教育・情報提供を目的としたサービスです。利益を保証するものではなく、投資の判断はご自身の責任で行ってください。</div>
</div>
</body>
</html>
"""

KAIGI_HTML = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>arbitrage — 社員会議室</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root{--ink:#16202e;--paper:#faf8f3;--surface:#ffffff;--jade:#0f7a5f;--jade-soft:#e3f1ec;--amber:#b5751a;--amber-soft:#f6ecdb;--muted:#5d6470;--border:#e7e2d7;--border-strong:#d8d2c4;}
*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);line-height:1.7;font-family:'Noto Sans JP',system-ui,'Hiragino Sans','Yu Gothic',sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:720px;margin:0 auto;padding:24px 18px 60px}
.topbar{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:18px}
.brand{font-size:22px;font-weight:700;letter-spacing:.5px}
.badge{font-size:12px;font-weight:500;color:var(--jade);background:var(--jade-soft);padding:5px 11px;border-radius:999px}
.hero{font-size:24px;font-weight:700;margin:0 0 6px}
.lead{font-size:14px;color:var(--muted);margin:0 0 18px}
.label{font-size:13px;color:var(--muted);margin:0 0 8px;font-weight:500}
.langs{display:flex;gap:6px;margin-bottom:14px;flex-wrap:wrap}
.lang{font-size:13px;padding:6px 12px;border-radius:999px;border:1px solid var(--border-strong);background:var(--surface);color:var(--muted);cursor:pointer}
.lang.on{background:var(--ink);color:#fff;border-color:var(--ink);font-weight:500}
textarea{width:100%;min-height:84px;font-family:inherit;font-size:15px;padding:14px;border:1px solid var(--border-strong);border-radius:12px;background:var(--surface);resize:vertical}
.start{width:100%;margin-top:12px;font-family:inherit;font-size:16px;font-weight:500;padding:13px;border:0;border-radius:10px;background:var(--ink);color:#fff;cursor:pointer}
.start:disabled{opacity:.5;cursor:default}
#meeting{margin-top:22px;display:flex;flex-direction:column;gap:12px}
.bub{background:var(--surface);border:1px solid var(--border);border-radius:14px;padding:14px 16px}
.bub.think{opacity:.7}
.who{display:flex;align-items:center;gap:9px;margin-bottom:7px}
.bemo{font-size:20px}
.bname{font-weight:700;font-size:14px;color:var(--jade)}
.btext{font-size:14.5px;white-space:pre-wrap}
.endnote{background:var(--amber-soft);border:1px solid #ecdcc0;border-radius:12px;padding:12px 14px;font-size:13px;color:var(--muted)}
.foot{margin-top:24px;border-top:1px solid var(--border);padding-top:14px;font-size:12px;color:var(--muted)}
</style>
</head>
<body>
<div class="wrap">
<p style="margin:0 0 14px"><a href="/" style="font-size:13px;color:#0f7a5f;text-decoration:none">← arbitrage トップへ</a></p>
<div class="topbar"><span class="brand">arbitrage</span><span class="badge">社員会議室</span></div>
<h1 class="hero">社員みんなで会議する</h1>
<p class="lead">あなたの相談について、社員が一人ずつ順番に意見を出します。事実確認 → 分析 → 反対意見 → やさしくまとめ → 最終チェック、の順です。最初の一人が出るまで少し時間がかかることがあります。</p>
<p class="label">答えの言語</p>
<div class="langs" id="langs"><span class="lang on" data-l="ja">日本語</span><span class="lang" data-l="en">English</span><span class="lang" data-l="ko">한국어</span><span class="lang" data-l="zh">中文</span></div>
<p class="label">相談したいこと</p>
<textarea id="q" placeholder="例：はじめての投資。少額でつみたてを始めるか迷っています。"></textarea>
<button class="start" id="startBtn">会議を始める</button>
<div id="meeting"></div>
<div class="foot">これは教育・情報提供を目的とした、AIによる会議形式の説明です。個別の売買アドバイスではなく、利益を保証するものでもありません。投資の判断はご自身の責任で行ってください。</div>
</div>
<script>
var lang="ja";var TOTAL=5;
var input=document.getElementById("q");var box=document.getElementById("meeting");var btn=document.getElementById("startBtn");
document.getElementById("langs").addEventListener("click",function(e){var b=e.target.closest(".lang");if(!b)return;lang=b.dataset.l;document.querySelectorAll("#langs .lang").forEach(function(x){x.classList.toggle("on",x===b);});});
function bubble(emoji,name,text,thinking){var d=document.createElement("div");d.className="bub"+(thinking?" think":"");d.innerHTML='<div class="who"><span class="bemo"></span><span class="bname"></span></div><div class="btext"></div>';d.querySelector(".bemo").textContent=emoji;d.querySelector(".bname").textContent=name;d.querySelector(".btext").textContent=text;box.appendChild(d);window.scrollTo(0,document.body.scrollHeight);return d;}
async function run(){var q=input.value.trim();if(!q)return;btn.disabled=true;btn.textContent="会議中…";box.innerHTML="";var transcript="";for(var step=0;;step++){var t=bubble("💭","社員が考えています…","",true);var data;try{var r=await fetch("/meeting",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({question:q,step:step,transcript:transcript,lang:lang})});data=await r.json();}catch(err){t.classList.remove("think");t.querySelector(".btext").textContent="通信でエラーが起きました。少し待ってもう一度ためしてください。";break;}if(data.error){t.classList.remove("think");t.querySelector(".btext").textContent="うまくいきませんでした："+data.error;break;}TOTAL=data.total;t.classList.remove("think");t.querySelector(".bemo").textContent=data.emoji;t.querySelector(".bname").textContent=data.speaker;t.querySelector(".btext").textContent=data.text;transcript+=data.speaker+"："+data.text+"\n\n";window.scrollTo(0,document.body.scrollHeight);if(step>=TOTAL-1)break;}var end=document.createElement("div");end.className="endnote";end.textContent="会議は以上です。各社員は最後に今のコンディションを ◎/○/△/×/? の5段階で示しています（とくに監査役カンサのまとめが総合判定です）。これは“今の条件の良し悪し”の目安であって、売買サインでも利益の保証でもありません。最終的な判断はご自身の責任で行ってください。";box.appendChild(end);btn.disabled=false;btn.textContent="もう一度 会議する";}
btn.addEventListener("click",run);
</script>
</body>
</html>
"""

@app.route("/")
def home():
    return Response(HOME_HTML, mimetype="text/html")

@app.route("/reception")
def analyst():
    return Response(ANALYST_HTML, mimetype="text/html")

@app.route("/practice")
def renshujo():
    return Response(RENSHUJO_HTML, mimetype="text/html")

@app.route("/basics")
def kihon():
    return Response(KIHON_HTML, mimetype="text/html")

@app.route("/factor")
def factor():
    return Response(FACTOR_HTML, mimetype="text/html")

@app.route("/arbitrage")
def arbitrage():
    return Response(ARBITRAGE_HTML, mimetype="text/html")

# ===== 練習市場室（ペーパー・暗号資産）=====
MARKET_HTML = r"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>取引所間 先物サヤ取り市場室 — arbitrage</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Hiragino Kaku Gothic ProN", Meiryo, sans-serif; margin:0; background:#0f1117; color:#e8eaed; line-height:1.7; }
  .wrap { max-width: 860px; margin:0 auto; padding:24px 18px 80px; }
  a.home { color:#9ab; text-decoration:none; font-size:14px; }
  h1 { font-size:24px; margin:14px 0 4px; }
  .sub { color:#9aa3b2; font-size:14px; margin:0 0 18px; }
  .motto { background:#1a2030; border:1px solid #2a3550; border-radius:12px; padding:12px 14px; font-size:14px; color:#cdd6e6; margin-bottom:18px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:10px; margin-bottom:18px; }
  .coin { background:#161b26; border:1px solid #232a39; border-radius:12px; padding:12px; }
  .coin .sym { font-weight:700; font-size:15px; }
  .coin .px { font-size:18px; margin-top:4px; }
  .up { color:#3ec78a; } .dn { color:#ff6b6b; }
  .coin .chg { font-size:13px; margin-top:2px; }
  .upd { color:#6b7689; font-size:12px; margin-bottom:14px; }
  .panel { background:#161b26; border:1px solid #232a39; border-radius:14px; padding:16px; margin-bottom:16px; }
  label { font-size:14px; color:#cdd6e6; display:block; margin-bottom:6px; }
  select, button { font-size:15px; border-radius:10px; padding:10px 12px; }
  select { background:#0f1117; color:#e8eaed; border:1px solid #2a3550; width:100%; margin-bottom:10px; }
  button.go { background:#3a6df0; color:#fff; border:none; cursor:pointer; width:100%; }
  button.go:disabled { opacity:.5; cursor:default; }
  .speak { background:#11161f; border:1px solid #232a39; border-left:3px solid #3a6df0; border-radius:10px; padding:12px 14px; margin-top:12px; }
  .speak .who { font-weight:700; font-size:14px; margin-bottom:4px; }
  .speak .body { font-size:14px; color:#dfe5ee; white-space:pre-wrap; }
  .note { font-size:13px; color:#8b94a6; margin-top:16px; }
  .err { color:#ff6b6b; font-size:14px; }
.judge { background:#11161f; border:1px solid #232a39; border-radius:14px; padding:14px 16px; margin-bottom:16px; }
.judge h2 { font-size:15px; margin:0 0 8px; color:#cdd6e6; }
.jrow { display:flex; align-items:center; gap:12px; margin-bottom:8px; flex-wrap:wrap; }
.jmark { font-size:30px; font-weight:700; line-height:1; }
.jlabel { font-size:15px; font-weight:700; }
.jreasons { font-size:13px; color:#aeb7c6; margin:0; padding-left:18px; }
.jreasons li { margin:2px 0; }
.jdisc { font-size:12px; color:#6b7689; margin-top:8px; }
</style></head><body><div class="wrap">
<h1>📈 取引所間 先物サヤ取り市場室</h1>
<p class="sub">複数取引所のリアルタイム価格を見て、社員たちが取引所間の先物価格差（アービトラージ）の観点から判断・分析する部屋です。</p>
<div class="motto">🧭 モットー：まちがいに早く気づく会社。ここは投資情報会社arbitrageの<strong>『取引所間 先物サヤ取り市場室』</strong>です。同じ先物の取引所間の価格差を、手数料・送金・税を引いた“手取り”の目線で判断・分析します。社員は「絶対もうかる」とは言わず、わからないことは正直に言います。投資の判断は、いつもあなた自身のものです。</div>
<div id="grid" class="grid"><div class="coin">読み込み中…</div></div>
<p id="upd" class="upd"></p>
<div class="judge">
<h2>🧭 今のコンディション自動判定（教育用・売買サインではありません）</h2>
<div class="jrow"><span id="jmark" class="jmark">?</span><span id="jlabel" class="jlabel">通貨を選んで判定します</span></div>
<ul id="jreasons" class="jreasons"></ul>
<p class="jdisc">これは本物の価格データを「プロの7か条」の物差しで見た“今の条件の良し悪し”の目安です。「確実に儲かる」という意味ではありません。最終判断はご自身で。</p>
  <p style="margin-top:8px"><a href="/log" style="color:#7ea8ff;font-size:13px">📜 過去の判定を振り返る（あのとき◎→その後どう動いたか）</a></p>
</div>
<div class="panel">
  <label>どの通貨を社員に分析してもらう？</label>
  <select id="sym">
    <option value="BTCUSDT">ビットコイン（BTC）</option>
    <option value="ETHUSDT">イーサリアム（ETH）</option>
    <option value="BNBUSDT">BNB</option>
    <option value="SOLUSDT">ソラナ（SOL）</option>
    <option value="XRPUSDT">リップル（XRP）</option>
  </select>
  <button id="go" class="go">この通貨を社員たちに分析してもらう</button>
  <div id="out"></div>
</div>
<p class="note">価格データ提供：Binanceの公開API（リアルタイム）。表示は米ドル建てです。これは教育・練習用で、売買のおすすめ（サイン）ではありません。情報はひとつだけでなく複数で確かめましょう。</p>
<script>
var API="https://api.binance.com";
var SYMS=["BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT"];
var NAMES={BTCUSDT:"BTC",ETHUSDT:"ETH",BNBUSDT:"BNB",SOLUSDT:"SOL",XRPUSDT:"XRP"};
function fmt(n){n=parseFloat(n);return n>=100?n.toLocaleString("en-US",{maximumFractionDigits:2}):n.toLocaleString("en-US",{maximumFractionDigits:4});}
async function loadGrid(){
  try{
    var url=API+"/api/v3/ticker/24hr?symbols="+encodeURIComponent(JSON.stringify(SYMS));
    var r=await fetch(url); var d=await r.json();
    var html="";
    d.forEach(function(x){
      var chg=parseFloat(x.priceChangePercent);
      var cls=chg>=0?"up":"dn"; var sign=chg>=0?"+":"";
      html+="<div class=\"coin\"><div class=\"sym\">"+NAMES[x.symbol]+"</div>"+
        "<div class=\"px "+cls+"\">$"+fmt(x.lastPrice)+"</div>"+
        "<div class=\"chg "+cls+"\">"+sign+chg.toFixed(2)+"% (24h)</div></div>";
    });
    document.getElementById("grid").innerHTML=html;
    var now=new Date();
    document.getElementById("upd").textContent="最終更新："+now.toLocaleTimeString("ja-JP")+"（数秒ごとに自動更新）";
  }catch(e){ document.getElementById("grid").innerHTML="<div class=\"coin err\">価格を取得できませんでした。</div>"; }
}
loadGrid(); setInterval(loadGrid, 10000); try{arbiFillResults();}catch(e){}
function arbiFillResults(){
  var KEY="arbi_judge_log";
  var log=[];try{log=JSON.parse(localStorage.getItem(KEY)||"[]");}catch(e){return;}
  if(!log||!log.length)return;
  var now=Date.now();
  var HRS={r1:3600000,r4:14400000,r24:86400000};
  var pending=[];
  for(var i=0;i<log.length;i++){var r=log[i];if(!r||!r.ts||!r.symbol)continue;
    var need=false;
    for(var k in HRS){if(r[k]===null||r[k]===undefined){if(now>=(r.ts+HRS[k]+60000))need=true;}}
    if(need)pending.push(i);
  }
  pending.sort(function(a,b){return log[a].ts-log[b].ts;});
  pending=pending.slice(0,20);
  if(!pending.length)return;
  var tasks=[];
  pending.forEach(function(idx){var r=log[idx];
    for(var k in HRS){if((r[k]===null||r[k]===undefined)&&now>=(r.ts+HRS[k]+60000)){
      var target=r.ts+HRS[k];var startTime=Math.floor(target/60000)*60000;
      tasks.push({idx:idx,key:k,sym:r.symbol,startTime:startTime,base:parseFloat(r.price)});
    }}
  });
  if(!tasks.length)return;
  var done=0;
  tasks.forEach(function(tk){
    var url=API+"/api/v3/klines"+"?"+"symbol"+"="+tk.sym+"&interval=1m&startTime="+tk.startTime+"&limit=1";
    fetch(url).then(function(res){return res.json();}).then(function(j){
      if(j&&j.length&&j[0]&&j[0][4]!==undefined){var close=parseFloat(j[0][4]);
        if(!isNaN(close)&&tk.base>0){var ch=(close-tk.base)/tk.base*100;log[tk.idx][tk.key]=Math.round(ch*1000)/1000;}}
    }).catch(function(){}).then(function(){
      done++;if(done===tasks.length){try{localStorage.setItem(KEY,JSON.stringify(log));}catch(e){}}
    });
  });
}
function renderJudge(snap){
  var jm=document.getElementById("jmark"), jl=document.getElementById("jlabel"), jr=document.getElementById("jreasons");
  var reasons=[]; var score=0; var TH={C1_LO:0.3,C1_HI:1.5,C1_MAX:2.5,C3_LO:1.2,C3_HI:6,C4_LO:0.8,C4_HI:1.8};
  try{
    var __c=(typeof closes!=='undefined'&&closes)?closes.map(parseFloat).filter(function(x){return !isNaN(x);}):[];
    if(__c.length>=3){
      var __r=[];for(var __i=1;__i<__c.length;__i++){if(__c[__i-1]>0)__r.push((__c[__i]-__c[__i-1])/__c[__i-1]*100);}
      if(__r.length){var __m=__r.reduce(function(a,b){return a+b;},0)/__r.length;var __v=Math.sqrt(__r.reduce(function(a,b){return a+(b-__m)*(b-__m);},0)/__r.length);
        if(__v>=TH.C1_LO&&__v<=TH.C1_HI)score+=1; else if(__v>TH.C1_MAX)score-=1;if(typeof __v==='number'&&!isNaN(__v)){if(__v>TH.C1_LO&&__v<TH.C1_HI)reasons.push("\u77ed\u3044\u8db3\u306e\u52d5\u304d\u304c"+__v.toFixed(2)+"%\u3067\u7a0b\u3088\u304f\u3001\u4fa1\u683c\u5dee\u304c\u51fa\u3064\u3064\u57f7\u884c\u3082\u9593\u306b\u5408\u3044\u3084\u3059\u3044\u3002");else if(__v>TH.C1_MAX)reasons.push("\u77ed\u3044\u8db3\u306e\u52d5\u304d\u304c"+__v.toFixed(2)+"%\u3068\u8352\u304f\u3001\u5dee\u304c\u3059\u3050\u52d5\u3044\u3066\u7d04\u5b9a\u524d\u306b\u6d88\u3048\u3084\u3059\u3044\u3002");else if(__v<=TH.C1_LO)reasons.push("\u77ed\u3044\u8db3\u306e\u52d5\u304d\u304c"+__v.toFixed(2)+"%\u3068\u3054\u304f\u5c0f\u3055\u304f\u3001\u4fa1\u683c\u5dee\u3082\u51fa\u306b\u304f\u3044\u3002");else reasons.push("\u77ed\u3044\u8db3\u306e\u52d5\u304d\u304c"+__v.toFixed(2)+"%\u3068\u3084\u3084\u5927\u304d\u3081\u3067\u3001\u69d8\u5b50\u898b\u306e\u6c34\u6e96\u3002");}
      }
      var __h=Math.floor(__c.length/2);
      if(__c.length>=4&&__c[0]>0&&__c[__h]>0){var __t1=(__c[__h-1]-__c[0])/__c[0]*100;var __t2=(__c[__c.length-1]-__c[__h])/__c[__h]*100;
        if((__t1>=0&&__t2>=0)||(__t1<0&&__t2<0))score+=1;if(typeof __t1==='number'&&typeof __t2==='number'&&!isNaN(__t1)&&!isNaN(__t2)){if((__t1>0&&__t2>0)||(__t1<0&&__t2<0))reasons.push("\u524d\u534a\u3068\u5f8c\u534a\u3067\u5024\u52d5\u304d\u306e\u5411\u304d\u304c\u305d\u308d\u3063\u3066\u304a\u308a\u3001\u6d41\u308c\u304c\u7d9a\u304d\u3084\u3059\u3044\u3002");else reasons.push("\u524d\u534a\u3068\u5f8c\u534a\u3067\u5024\u52d5\u304d\u306e\u5411\u304d\u304c\u98df\u3044\u9055\u3044\u3001\u6d41\u308c\u304c\u5b9a\u307e\u308a\u306b\u304f\u3044\u3002");}
      }
    }
  }catch(__e){}
  var __dummy=0; var ok=true;
  var price=parseFloat(snap.price), hi=parseFloat(snap.high24), lo=parseFloat(snap.low24), chg=parseFloat(snap.changePct);
  var closes=(snap.hourlyCloses||[]).map(Number).filter(function(x){return !isNaN(x);});
  if(isNaN(price)||isNaN(hi)||isNaN(lo)||closes.length<6){ ok=false; }
  // 1) ボラティリティ（24hの値幅）：サヤ取りは荒すぎると送金・約定が間に合わず危険、静かすぎると差が出ない
  var rangePct = (ok && hi>0)? ((hi-lo)/((hi+lo)/2))*100 : NaN;
  if(!isNaN(rangePct)){
    if(rangePct>=TH.C3_LO && rangePct<=TH.C3_HI){ score+=1; reasons.push("24hの値幅が"+rangePct.toFixed(1)+"%で、取引所間に差が出つつ執行も間に合いやすい水準。"); }
    else if(rangePct>TH.C3_HI){ score-=1; reasons.push("24hの値幅が"+rangePct.toFixed(1)+"%と荒い。差は出やすいが送金・約定が間に合わず、コストとリスクで手取りが消えやすい。"); }
    else { reasons.push("24hの値幅が"+rangePct.toFixed(1)+"%と静か。差が小さく、手数料・送金・税を引くと手取りが残りにくい。"); }
  }
  // 2) 直近トレンドの安定（終値の連続変化のばらつき）
  if(closes.length>=6){
    var rets=[]; for(var i=1;i<closes.length;i++){ rets.push((closes[i]-closes[i-1])/closes[i-1]); }
    var mean=rets.reduce(function(a,b){return a+b;},0)/rets.length;
    var varc=rets.reduce(function(a,b){return a+(b-mean)*(b-mean);},0)/rets.length;
    var sd=Math.sqrt(varc)*100;
    if(sd<=TH.C4_LO){ score+=1; reasons.push("直近の1時間ごとの動きが安定（ブレ"+sd.toFixed(2)+"%）で、価格差が読みやすい。"); }
    else if(sd>TH.C4_HI){ score-=1; reasons.push("直近の動きのブレが"+sd.toFixed(2)+"%と大きく、差がすぐ逆行・消失しやすい。"); }
    else { reasons.push("直近の動きのブレは"+sd.toFixed(2)+"%でふつう。"); }
  }
  // 3) コスト負けの注意（常に効く物差し）
  reasons.push("見かけの差ではなく、両側の手数料＋送金料＋税を引いた“手取り”で残るかが判断の核（利幅は1取引1〜1.5%程度と薄い）。");
  // 4) 取引所まわりのリスク注意
  reasons.push("資金は1か所に集中させない・送金が絡む取引は避ける・異常時に止まる安全装置を持つ——相場以外のリスクで死なないことが最優先。");
  var mark, label, color;
  if(!ok){ mark="?"; label="データ不足でわからない"; color="#9aa3b2"; }
  else if(score>=2){ mark="◎"; label="条件はとても良い（あくまで“良し悪し”の目安）"; color="#3ec78a"; }
  else if(score===1){ mark="○"; label="条件は良いほう"; color="#3ec78a"; }
  else if(score===0){ mark="△"; label="微妙・様子見"; color="#d9a441"; }
  else { mark="×"; label="今は条件が良くない"; color="#ff6b6b"; }
  jm.textContent=mark; jm.style.color=color; jl.textContent=label;  jl.style.color=color;
  try{
    var __key="arbi_judge_log";
    var __log=JSON.parse(localStorage.getItem(__key)||"[]");
    var __now=Date.now();
    var __sym=(snap&&snap.symbol)||"?";
    var __last=__log.length?__log[__log.length-1]:null;
    if(!(__last&&__last.symbol===__sym&&(__now-__last.ts)<60000)){
      var __tf=(snap&&snap.trendFirstHalf);var __ts2=(snap&&snap.trendSecondHalf);var __dir='neutral';if(typeof __tf==='number'&&typeof __ts2==='number'){var __dd=__ts2-__tf;if(__dd>0.1)__dir='up';else if(__dd<-0.1)__dir='down';}var __conds=[];try{if(typeof ok!=='undefined' && ok===false){__conds.push({id:'G',dir:0});}else{if(typeof __v==='number' && !isNaN(__v)){if(__v>TH.C1_LO && __v<TH.C1_HI)__conds.push({id:'C1',dir:1});else if(__v>TH.C1_MAX)__conds.push({id:'C1',dir:-1});else __conds.push({id:'C1',dir:0});}if(typeof __t1==='number' && typeof __t2==='number' && !isNaN(__t1) && !isNaN(__t2)){if((__t1>0&&__t2>0)||(__t1<0&&__t2<0))__conds.push({id:'C2',dir:1});else __conds.push({id:'C2',dir:0});}if(typeof rangePct==='number' && !isNaN(rangePct)){if(rangePct>TH.C3_LO && rangePct<TH.C3_HI)__conds.push({id:'C3',dir:1});else if(rangePct>TH.C3_HI)__conds.push({id:'C3',dir:-1});else __conds.push({id:'C3',dir:0});}if(typeof sd==='number' && !isNaN(sd)){if(sd<TH.C4_LO)__conds.push({id:'C4',dir:1});else if(sd>TH.C4_HI)__conds.push({id:'C4',dir:-1});else __conds.push({id:'C4',dir:0});}}}catch(__ce){}__log.push({ts:__now,symbol:__sym,source:'binance-spot',price:(snap&&snap.price)||null,changePct:(snap&&snap.changePct)||null,mark:mark,label:label,trendDir:__dir,r1:null,r4:null,r24:null,conds:__conds});
      if(__log.length>2000)__log=__log.slice(__log.length-2000);
      localStorage.setItem(__key,JSON.stringify(__log));
    }
  }catch(__e){}
  jr.innerHTML=reasons.map(function(t){var li=document.createElement("li");li.textContent=t;return li.outerHTML;}).join("");
}
var goBtn=document.getElementById("go");
goBtn.onclick=async function(){
  var sym=document.getElementById("sym").value;
  var out=document.getElementById("out"); out.innerHTML="";
  goBtn.disabled=true; goBtn.textContent="社員たちが分析中…";
  try{
    var tr=await fetch(API+"/api/v3/ticker/24hr?symbol="+sym).then(r=>r.json());
    var kl=await fetch(API+"/api/v3/klines?symbol="+sym+"&interval=1h&limit=24").then(r=>r.json());
    var closes=kl.map(function(k){return parseFloat(k[4]);});
    var snapshot={symbol:NAMES[sym],price:tr.lastPrice,changePct:tr.priceChangePercent,high24:tr.highPrice,low24:tr.lowPrice,hourlyCloses:closes,quoteVolume:(tr.quoteVolume||tr.volume||null),trades:(tr.count!=null?tr.count:null),wap:(tr.weightedAvgPrice||null),volPct:(function(){if(!closes||closes.length<3)return null;var r=[];for(var k=1;k<closes.length;k++){var a=parseFloat(closes[k-1]),b=parseFloat(closes[k]);if(a>0)r.push((b-a)/a*100);}if(!r.length)return null;var m=r.reduce(function(x,y){return x+y;},0)/r.length;var v=r.reduce(function(x,y){return x+(y-m)*(y-m);},0)/r.length;return Math.sqrt(v);})(),trendFirstHalf:(function(){if(!closes||closes.length<4)return null;var h=Math.floor(closes.length/2);var a=parseFloat(closes[0]),b=parseFloat(closes[h-1]);if(a>0)return (b-a)/a*100;return null;})(),trendSecondHalf:(function(){if(!closes||closes.length<4)return null;var h=Math.floor(closes.length/2);var a=parseFloat(closes[h]),b=parseFloat(closes[closes.length-1]);if(a>0)return (b-a)/a*100;return null;})()};
renderJudge(snapshot);
    var transcript=""; var step=0; var total=999;
    var histStr=(function(){try{var lg=JSON.parse(localStorage.getItem('arbi_judge_log')||'[]');var sym=(snapshot&&snapshot.symbol)||'';var cur=(snapshot&&snapshot.price)||null;var rows=lg.filter(function(e){return e&&e.symbol===sym&&e.price&&e.mark&&e.ts;});if(!rows.length||!cur)return '';var byMark={};rows.forEach(function(e){var ch=((cur-e.price)/e.price)*100;if(!byMark[e.mark])byMark[e.mark]={n:0,up:0,sum:0};byMark[e.mark].n++;byMark[e.mark].sum+=ch;if(ch>0)byMark[e.mark].up++;});var lines=['\u3010\u904e\u53bb\u306e\u81ea\u5206\u305f\u3061\u306e\u5224\u5b9a\u5b9f\u7e3e\uff08\u540c\u3058\u901a\u8ca8\u30fb\u53c2\u8003\u60c5\u5831\uff09\u3011'];['\u25ce','\u25cb','\u25b3','\u00d7','?'].forEach(function(m){var d=byMark[m];if(!d)return;var avg=(d.sum/d.n).toFixed(2);var rate=Math.round((d.up/d.n)*100);lines.push('\u5224\u5b9a'+m+'\uff1a'+d.n+'\u4ef6\u3002\u305d\u306e\u5f8c\u3001\u73fe\u5728\u5024\u307e\u3067\u5e73\u5747'+avg+'%\uff08\u4e0a\u6607\u3057\u305f\u5272\u5408'+rate+'%\uff09');});if(lines.length<2)return '';lines.push('\u203b\u3053\u308c\u306f\u904e\u53bb\u306e\u50be\u5411\u306e\u53c2\u8003\u3067\u3042\u308a\u3001\u672a\u6765\u3092\u4fdd\u8a3c\u3059\u308b\u3082\u306e\u3067\u306f\u3042\u308a\u307e\u305b\u3093\u3002\u58f2\u8cb7\u30b5\u30a4\u30f3\u3067\u306f\u3042\u308a\u307e\u305b\u3093\u3002');return lines.join('\n');}catch(e){return '';}})();
      while(step<total){
      var res=await fetch("/market_analyze",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({snapshot:snapshot,step:step,transcript:transcript,history:histStr})});
      var j=await res.json();
      if(j.error){ out.innerHTML+="<div class=\"speak err\">"+j.error+"</div>"; break; }
      total=j.total;
      var div=document.createElement("div"); div.className="speak";
      div.innerHTML="<div class=\"who\">"+j.who+"</div><div class=\"body\"></div>";
      div.querySelector(".body").textContent=j.text;
      out.appendChild(div);
      transcript+=j.who+"："+j.text+"\n";
      step++;
    }
  }catch(e){ out.innerHTML+="<div class=\"speak err\">分析中にエラーが起きました。少し待ってからもう一度ためしてください。</div>"; }
  goBtn.disabled=false; goBtn.textContent="この通貨を社員たちに分析してもらう";
};
</script>
</div></body></html>"""

# 分析に参加する社員（順番に発言する）
LOG_HTML = r"""<!doctype html><html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>判定の振り返り — arbitrage</title>
<style>
body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;max-width:880px;margin:0 auto;padding:24px;background:#0b0e14;color:#e6e6e6;line-height:1.7}
a{color:#7ea8ff}h1{font-size:22px}.muted{color:#8a93a3;font-size:14px}
.card{background:#141925;border:1px solid #232b3a;border-radius:12px;padding:16px;margin:14px 0}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:8px 6px;border-bottom:1px solid #232b3a}
.mark{font-size:18px;font-weight:bold}.up{color:#3ddc84}.down{color:#ff6b6b}.flat{color:#cbd2e0}
.note{background:#10151f;border:1px dashed #2c3547;border-radius:10px;padding:12px;color:#9aa3b2;font-size:13px;margin:12px 0}
.btn{display:inline-block;background:#2b6cff;color:#fff;padding:8px 14px;border-radius:8px;text-decoration:none;border:none;cursor:pointer;font-size:14px}
</style></head><body>
<p><a href="/market">&larr; 市場室へ</a> &nbsp; <a href="/">arbitrage トップ</a></p>
<h1>📜 判定の振り返り（社員たちが向上するための記録）</h1>
<p class="muted">市場室で出した自動判定（◎○△×?）を、この端末に記録しています。後から「あのとき◎と言ったが、その後どう動いたか」を今の価格と見比べて、次に活かすためのページです。これは教育用で、売買のおすすめではありません。</p>
<div class="note">※ 記録はこの端末（ブラウザ）の中だけに保存され、外部には送信されません。市場室で判定するほど記録が増えます。</div>
<div class="card"><div id="summary" class="muted">読み込み中…</div></div><div class="card"><div id="summary2" class="muted">答え合わせ集計を計算中…</div></div><div class="card"><div id="board"></div></div><div class="card"><div id="cboard"></div></div>
<div class="card"><table><thead><tr><th>日時</th><th>通貨</th><th>判定</th><th>当時の価格</th><th>今の価格</th><th>その後</th></tr></thead><tbody id="rows"><tr><td colspan="6" class="muted">記録がまだありません。市場室で判定してみてください。</td></tr></tbody></table></div>
<p><button class="btn" id="exportBtn">バックアップを保存</button> <button class="btn" id="importBtn">バックアップから復元</button><input type="file" id="importFile" accept="application/json,.json" style="display:none"></p>
<p><button class="btn" id="clearBtn">記録を消す</button></p>
<script>
var B="https://"+"api."+"binance"+".com";
function fmt(n){n=parseFloat(n);return isNaN(n)?"?":n.toLocaleString("en-US",{maximumFractionDigits:2});}
function symPair(sym){return (sym&&sym!=="?")?(sym+"USDT"):null;}
function load(){
  var log=[];try{log=JSON.parse(localStorage.getItem("arbi_judge_log")||"[]");}catch(e){}
  var rows=document.getElementById("rows");
  var summ=document.getElementById("summary");
  if(!log.length){summ.textContent="まだ記録がありません。市場室で「判定」するとここに貯まります。";return;}
  summ.textContent="記録 "+log.length+" 件。◎/○ は「条件が良い」と評価したとき、× は「良くない」と評価したときの目安です。当てる記録ではなく、判断を見直すための記録です。";
  var html="";
  for(var i=log.length-1;i>=0;i--){var r=log[i];var d=new Date(r.ts);var then=parseFloat(r.price);
    var mk=r.mark||"?";var mcls=(mk==="◎"||mk==="○")?"up":(mk==="×"?"down":"flat");
    html+="<tr data-sym='"+(r.symbol||"?")+"' data-then='"+(isNaN(then)?"":then)+"'><td class=muted>"+d.toLocaleString("ja-JP")+"</td><td>"+(r.symbol||"?")+"</td><td class='mark "+mcls+"'>"+mk+"</td><td>$"+fmt(then)+"</td><td class='nowp'>…</td><td class='aft'>…</td></tr>";
  }
  rows.innerHTML=html;
  (function(){
    var obs=[];
    log.forEach(function(r){["r1","r4","r24"].forEach(function(k){var v=r[k];if(v!==null&&v!==undefined&&!isNaN(v)){obs.push({ch:parseFloat(v),dir:r.trendDir||"neutral"});}});});
    var sum=document.getElementById("summary2");if(!sum)return;
    if(!obs.length){sum.textContent="答え合わせ済みデータがまだありません（1時間以上経過した判定から自動で埋まります）。";return;}
    var dirObs=obs.filter(function(o){return o.dir==="up"||o.dir==="down";});
    var dirHit=dirObs.filter(function(o){return (o.dir==="up"&&o.ch>0)||(o.dir==="down"&&o.ch<0);}).length;
    var moveHit=obs.filter(function(o){return Math.abs(o.ch)>=0.3;}).length;
    var p1=dirObs.length?Math.round(dirHit/dirObs.length*1000)/10:null;
    var p2=Math.round(moveHit/obs.length*1000)/10;
    var msg="答え合わせ "+obs.length+"件（1h/4h/24h後の値動き）｜トレンド方向に動いた率: "+(p1===null?"—":p1+"%")+"（対象"+dirObs.length+"件）｜方向不問で±0.3%以上動いた率: "+p2+"%";
    sum.textContent=msg;
  })();

  var syms=[];log.forEach(function(r){var p=symPair(r.symbol);if(p&&syms.indexOf(p)<0)syms.push(p);});
  syms.forEach(function(p){
    fetch(B+"/api/v3/ticker/price?symbol="+p).then(function(res){return res.json();}).then(function(j){
      var now=parseFloat(j.price);var sym=p.replace("USDT","");
      var trs=document.querySelectorAll("tr[data-sym='"+sym+"']");
      trs.forEach(function(tr){var then=parseFloat(tr.getAttribute("data-then"));var nc=tr.querySelector(".nowp");var ac=tr.querySelector(".aft");
        if(nc)nc.textContent=now?"$"+fmt(now):"?";
        if(ac&&now&&then&&then>0){var ch=(now-then)/then*100;ac.textContent=(ch>=0?"+":"")+ch.toFixed(2)+"%";ac.className="aft "+(ch>0.05?"up":(ch<-0.05?"down":"flat"));}
        else if(ac){ac.textContent="—";}
      });
    }).catch(function(){});
  });
}
document.getElementById("clearBtn").onclick=function(){if(confirm("この端末の判定記録をすべて消しますか？")){localStorage.removeItem("arbi_judge_log");location.reload();}};
var BK_KEY="arbi_judge_log";
function bkRead(){try{return JSON.parse(localStorage.getItem(BK_KEY)||"[]")||[];}catch(e){return [];}}
function bkDate(){var d=new Date();function p(n){return (n<10?"0":"")+n;}return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate());}
var __eb=document.getElementById("exportBtn");
if(__eb){__eb.onclick=function(){
  var data=bkRead();
  var payload={format:"v1",exportedAt:new Date().toISOString(),count:data.length,data:data};
  var blob=new Blob([JSON.stringify(payload,null,2)],{type:"application/json"});
  var url=URL.createObjectURL(blob);
  var a=document.createElement("a");a.href=url;a.download="arbi_backup_"+bkDate()+".json";
  document.body.appendChild(a);a.click();document.body.removeChild(a);
  setTimeout(function(){URL.revokeObjectURL(url);},1000);
};}
var __ib=document.getElementById("importBtn");var __if=document.getElementById("importFile");
if(__ib&&__if){
  __ib.onclick=function(){__if.value="";__if.click();};
  __if.onchange=function(){
    var file=__if.files&&__if.files[0];if(!file)return;
    var reader=new FileReader();
    reader.onload=function(){
      var obj;try{obj=JSON.parse(reader.result);}catch(e){alert("読み込み失敗：JSONを解析できませんでした。");return;}
      if(!obj||obj.format!=="v1"){alert("形式が違います（v1のバックアップではありません）。");return;}
      var incoming=(obj&&obj.data)||[];if(!(incoming instanceof Array)){alert("データ形式が不正です。");return;}
      var cur=bkRead();
      var seen={};for(var i=0;i<cur.length;i++){var c=cur[i];if(c&&c.ts!=null&&c.symbol!=null){seen[c.ts+"|"+c.symbol]=true;}}
      var add=[],skip=0;
      for(var j=0;j<incoming.length;j++){
        var e=incoming[j];
        if(!e||e.ts==null||e.symbol==null||e.price==null||e.mark==null){skip++;continue;}
        var k=e.ts+"|"+e.symbol;
        if(seen[k]){continue;}
        seen[k]=true;add.push(e);
      }
      if(add.length===0){alert("追加できる新しい記録はありませんでした（現在 "+cur.length+" 件、スキップ "+skip+" 件）。");return;}
      if(!confirm("現在 "+cur.length+" 件、追加されるのは "+add.length+" 件（スキップ "+skip+" 件）。実行しますか？")){return;}
      var merged=cur.concat(add);
      merged.sort(function(a,b){return (a.ts||0)-(b.ts||0);});
      localStorage.setItem(BK_KEY,JSON.stringify(merged));
      location.reload();
    };
    reader.readAsText(file);
  };
}

var BOARD_MOVE_THRESH=0.3;
var __boardHorizon="r1";
var BOARD_HKEYS=[["r1","1時間後"],["r4","4時間後"],["r24","24時間後"]];
var BOARD_MARKS=["◎","○","△","×","？"];
function boardRead(){try{return JSON.parse(localStorage.getItem("arbi_judge_log")||"[]")||[];}catch(e){return [];}}
function boardPct(n,d){return d?(Math.round(n/d*1000)/10):null;}
function drawBoard(){
  var el=document.getElementById("board");if(!el)return;
  var log=boardRead();
  var hk=__boardHorizon;
  var any=false;
  for(var i=0;i<log.length;i++){var v=log[i]&&log[i][hk];if(v!=null&&v!==undefined&&!isNaN(v)){any=true;break;}}
  var btns="";for(var b=0;b<BOARD_HKEYS.length;b++){var hkk=BOARD_HKEYS[b][0];var hlbl=BOARD_HKEYS[b][1];btns+='<button class="btn'+(hkk===hk?" on":"")+'" data-hz="'+hkk+'" style="margin-right:6px">'+hlbl+'</button>';}
  var head='<div style="margin-bottom:8px">'+btns+'</div>';
  if(!any){el.innerHTML=head+'<div class="muted">まだ成績データがありません。判定が記録され、時間が経つとここに表示されます。</div>';boardBind();return;}
  var rowsHtml="";
  for(var m=0;m<BOARD_MARKS.length;m++){
    var mk=BOARD_MARKS[m];
    var cnt=0,dirN=0,dirHit=0,moveHit=0,absSum=0;
    for(var j=0;j<log.length;j++){
      var r=log[j];if(!r||r.mark!==mk)continue;
      var v=r[hk];if(v==null||v===undefined||isNaN(v))continue;
      var ch=parseFloat(v);cnt++;absSum+=Math.abs(ch);
      if(Math.abs(ch)>=BOARD_MOVE_THRESH)moveHit++;
      var dir=r.trendDir||"neutral";
      if(dir==="up"||dir==="down"){dirN++;if((dir==="up"&&ch>0)||(dir==="down"&&ch<0))dirHit++;}
    }
    var p1=boardPct(dirHit,dirN);var p2=boardPct(moveHit,cnt);
    var avg=cnt?(Math.round(absSum/cnt*100)/100):null;
    var few=(cnt>0&&cnt<30)?' <span class="muted">件数僅少（参考値）</span>':"";
    rowsHtml+="<tr><td>"+mk+"</td><td>"+cnt+few+"</td><td>"+(p1==null?"—":p1+"%")+"</td><td>"+(p2==null?"—":p2+"%")+"</td><td>"+(avg==null?"—":avg+"%")+"</td></tr>";
  }
  var tbl='<table><thead><tr><th>印</th><th>件数</th><th>方向的中率</th><th>±0.3%以上</th><th>平均変化幅</th></tr></thead><tbody>'+rowsHtml+"</tbody></table>";
  el.innerHTML=head+tbl;
  boardBind();
}
function boardBind(){
  var el=document.getElementById("board");if(!el)return;
  var bs=el.querySelectorAll("button[data-hz]");
  for(var i=0;i<bs.length;i++){bs[i].onclick=function(){__boardHorizon=this.getAttribute("data-hz");drawBoard();};}
}
var __cHorizon="r1";var CB_HKEYS=[["r1","1\u6642\u9593\u5f8c"],["r4","4\u6642\u9593\u5f8c"],["r24","24\u6642\u9593\u5f8c"]];var CB_IDS=["C1","C2","C3","C4"];var CB_NAMES={C1:"C1 \u77ed\u671f\u30dc\u30e9",C2:"C2 \u524d\u5f8c\u534a\u30c8\u30ec\u30f3\u30c9\u4e00\u81f4",C3:"C3 24h\u5024\u5e45",C4:"C4 \u6642\u9593\u8db3sd"};function cbDirLabel(d){return d>0?"+1":(d<0?"-1":"0");}function drawCBoard(){var el=document.getElementById("cboard");if(!el)return;var log=boardRead();var hk=__cHorizon;var gFire=0;var anyData=false;var buckets={};for(var i=0;i<log.length;i++){var r=log[i];if(!r||!r.conds||!r.conds.length)continue;var hasG=false;for(var g=0;g<r.conds.length;g++){if(r.conds[g]&&r.conds[g].id==="G")hasG=true;}if(hasG){gFire++;continue;}var v=r[hk];if(v===null||v===undefined||isNaN(v))continue;var ch=parseFloat(v);anyData=true;for(var c=0;c<r.conds.length;c++){var cd=r.conds[c];if(!cd||CB_IDS.indexOf(cd.id)<0)continue;var key=cd.id+"|"+cd.dir;if(!buckets[key])buckets[key]={id:cd.id,dir:cd.dir,cnt:0,dirN:0,dirHit:0,moveHit:0,absSum:0};var bk=buckets[key];bk.cnt++;bk.absSum+=Math.abs(ch);if(cd.dir!==0){if(Math.abs(ch)>=BOARD_MOVE_THRESH)bk.moveHit++;var dir=r.trendDir||"neutral";if(dir==="up"||dir==="down"){bk.dirN++;if((dir==="up"&&ch>0)||(dir==="down"&&ch<0))bk.dirHit++;}}}}var btns="";for(var b=0;b<CB_HKEYS.length;b++){var hkk=CB_HKEYS[b][0];var hlbl=CB_HKEYS[b][1];btns+='<button class="btn'+(hkk===hk?" on":"")+'" data-chz="'+hkk+'" style="margin-right:6px">'+hlbl+'</button>';}var head='<h3 style="margin:0 0 8px">\u6761\u4ef6\u5225\u306e\u6210\u7e3e</h3><div style="margin-bottom:8px">'+btns+'</div>';if(!anyData){el.innerHTML=head+'<div class="muted">\u307e\u3060\u6761\u4ef6\u5225\u30c7\u30fc\u30bf\u304c\u3042\u308a\u307e\u305b\u3093\u3002\u2463-A\u4ee5\u964d\u306e\u5224\u5b9a\u304c\u7b54\u3048\u5408\u308f\u305b\u3055\u308c\u308b\u3068\u3053\u3053\u306b\u8868\u793a\u3055\u308c\u307e\u3059</div>'+'<div class="muted" style="margin-top:6px">G\u30b2\u30fc\u30c8\u767a\u706b: '+gFire+'\u56de</div>';cboardBind();return;}var rowsHtml="";var order=[1,-1,0];for(var k=0;k<CB_IDS.length;k++){var id=CB_IDS[k];for(var o=0;o<order.length;o++){var dv=order[o];var bk=buckets[id+"|"+dv];if(!bk)continue;var p1=(dv!==0)?boardPct(bk.dirHit,bk.dirN):null;var p2=(dv!==0)?boardPct(bk.moveHit,bk.cnt):null;var avg=bk.cnt?(Math.round(bk.absSum/bk.cnt*100)/100):null;var few=(bk.cnt>0&&bk.cnt<30)?' <span class="muted">\u4ef6\u6570\u50fc\u5c11\uff08\u53c2\u8003\u5024\uff09</span>':"";var c1=(dv===0)?"\u2014":(p1===null?"\u2014":p1+"%");var c2=(dv===0)?"\u2014":(p2===null?"\u2014":p2+"%");var c3=(avg===null?"\u2014":avg+"%");rowsHtml+="<tr><td>"+CB_NAMES[id]+"</td><td>"+cbDirLabel(dv)+"</td><td>"+bk.cnt+few+"</td><td>"+c1+"</td><td>"+c2+"</td><td>"+c3+"</td></tr>";}}var tbl='<table><thead><tr><th>\u6761\u4ef6</th><th>\u767a\u706b</th><th>\u4ef6\u6570</th><th>\u65b9\u5411\u7684\u4e2d\u7387</th><th>\u00b10.3%\u4ee5\u4e0a</th><th>\u5e73\u5747\u5909\u5316\u5e45</th></tr></thead><tbody>'+rowsHtml+'</tbody></table>';var gline='<div class="muted" style="margin-top:6px">G\u30b2\u30fc\u30c8\u767a\u706b: '+gFire+'\u56de\uff08\u6210\u7e3e\u8a08\u7b97\u5bfe\u8c61\u5916\uff09</div>';el.innerHTML=head+tbl+gline;cboardBind();}function cboardBind(){var el=document.getElementById("cboard");if(!el)return;var bs=el.querySelectorAll("button[data-chz]");for(var i=0;i<bs.length;i++){bs[i].onclick=function(){__cHorizon=this.getAttribute("data-chz");drawCBoard();};}}drawCBoard();
drawBoard();
load();
</script></body></html>"""

MARKET_TEAM = [
    {"key": "checker", "name": "事実確認係ハジメ", "job": "各取引所から渡された実データ（今の価格・気配・出来高感・直近の値動き）を正しく読み、どの数字をどう見るかを実演する。思い込みを足さない。出どころ・鮮度・一情報源だけ、を警告し、最新値は持たないと正直に言い、確認は本人に促す。"},
    {"key": "spread", "name": "価格差ウォッチャー サヤミ⚖️", "job": "同じ先物が取引所Aと取引所Bでいくら違うか（価格差・乖離）を見て、差が開いているか・縮みそうかを評価する。狙うのは相場の上下を当てることではなく、取引所間の歪みを取ること。ただし『見かけの価格差』はコストで消えやすいので、差があるというだけでは“いい”と言わない。差の大きさ・続きそうかをどう見るか具体的に示す。"},
    {"key": "cost", "name": "コスト精査役 テスリ🧮", "job": "両側の取引手数料＋送金料＋税を全部引いて、それでも『手取りで残る差』になる時だけを“いい”とする。利幅は1取引1〜1.5%程度と薄い前提で、コストでサヤが消える落とし穴を必ずセットで示す。見かけの差ではなく手取りの差で語る。"},
    {"key": "transfer", "name": "送金・約定リスク係 オクリ🚚", "job": "送金にかかる時間・出金停止のリスク・約定スピード/スリッページ・取引所の信用リスクを点検する。速く正確に両側を執行できない時は『今はよくない』と見送る。サヤがある間に実際に動かせるのか、を現実目線で問う。"},
    {"key": "liq", "name": "清算・レバレッジ係 セイサン⚠️", "job": "先物特有のレバレッジ清算・必要証拠金・（パーペチュアルなら）ファンディングの影響を点検する。無理なレバレッジや証拠金不足で、サヤを取る前に清算される危険を止める。レバは控えめに、を貫く。"},
    {"key": "spread2", "name": "資金分散係 ブンサン📦", "job": "資金を1取引所に集中させない、出金詰まり・取引所トラブルに備えて分散できているかを見る。一つの取引所に依存した計画には釘を刺す。"},
    {"key": "history", "name": "歴史係コヨミ📜", "job": "過去の取引所破綻・価格乖離の急拡大・サヤが一気に消えた例から、サヤ取りトレーダーが何で間違えやすかったか注意点をそえる。予言はしない。歴史は同じには繰り返さないと添える。"},
    {"key": "devil", "name": "悪魔の代弁者アマノジャク😈", "job": "取引所間サヤ取りの最悪ケース（差が逆行する・送金詰まり・出金停止・レバレッジ清算・コストで差が消える）を必ず具体的に問い、楽観のまちがいに早く気づかせる。『絶対』『鉄板』『リスクなしのもうけ』を強く疑い、断定が出たら止める。"},
    {"key": "audit", "name": "監査役カンサ🔍", "job": "最後に全員の発言を総点検する、ミス発見が最上級のプロ。サヤ取り特有の甘い見積もり（手数料・送金料・税の軽視、価格差の過大評価、執行スピードの楽観）に赤ペンを入れ、次に本人が確認すべきことを1つ示し、これは練習であって個別の売買指示ではない／最終判断は本人、と念押しして締める。利用者を守る。"},
]

def build_market_system(member, lang):
    lang_name = LANG_NAMES.get(lang, "日本語")
    parts = [
        RULES,
        "",
        SEVEN_RULES,
        "",
        REASON_RULES,
        "",
        CONFLUENCE_RULES,
        "",
        "ここは投資情報会社arbitrageの『取引所間 先物サヤ取り市場室』です。複数取引所のリアルタイム価格データを見て、取引所間の先物価格差（アービトラージ）の観点から判断・分析する場です。",
        "あなたは世界最上級のプロです。プロの中でも、とりわけ『自分のまちがいに、誰よりも早く気づく』ことに長けた一流です。社員「" + member["name"] + "」として発言します。あなたの役割：" + member["job"],
        "",
        "【全手法共通のマンデート（判断の物差し）】",
        "・1回の判断で許容する損失の上限は資金の0.5〜1%、1日の最大損失は2%（ここを超えたらその日は打ち切り）、月間の最大ドローダウンは10%（ここを割ったら一旦止めて報告）、という損失ラインを階層で守る。",
        "・評価軸は『毎日勝つこと』ではなく『月間・年間でトータルでプラス、かつ損益の振れ幅（ボラティリティ）を抑えること』。チャンスがない時は、入らず待つことも正しい判断とする。",
        "・各判断では、入る根拠・想定する損切り幅・利確幅・その時の損益の振れを、手数料やコストを引いた“手取り”の目線で考える。",
        "・【取引所間サヤ取り専用ルール】狙うのは相場の上下当てではなく、同じ先物の取引所間の価格差。両側の取引手数料＋送金料＋税を全部引いて『手取りで残る差』になる時だけを“いい”とし、見かけの価格差では判断しない。",
        "・送金にかかる時間・出金停止のリスク・約定スピード/スリッページ・取引所の信用リスクを必ず織り込む。速く正確に両側を執行できない時は見送る。",
        "・資金を1取引所に集中させない。先物のレバレッジは控えめにし、清算・証拠金・（パーペチュアルなら）ファンディングの影響に注意する。利幅は1取引1〜1.5%程度と薄い前提で、薄い差を安定して積み上げる発想。",
        "",
        "最上級のプロとして、毎回かならず自分の分析を自己点検します：",
        "・自分が今出した見方の『いちばん弱いところ・あやしいところ』を、自分で1つ挙げる。",
        "・自分の思い込みを疑う（後知恵バイアス、生存バイアス、たまたま当たっただけ、直近の動きに引きずられる、など）。",
        "・『この分析がまちがっているとしたら、どんな時か』を必ず1つ言う。",
        "・前の人の発言で、あやしい点・言いすぎ・根拠の弱い所があれば、遠慮なく・ていねいに指摘する（ただ褒め合わない）。",
        "",
        "必ず守ること（一流ほど厳しく守る）：",
        "・「絶対上がる/絶対下がる」「確実にもうかる」とは絶対に言わない。確実な利益は存在しない。",
        "・わからないことは正直に「わからない」と言う。数字をでっち上げない。プロほど『わからない』を恐れない。",
        "・買う/売るの個別サイン（これを買え/売れ・いくらで指値しろ等）は出さない。代わりに、いまの状況が各手法にとって良いか・良くないか（例：今は流動性があって条件がいい／今は薄くてよくない）を述べる。",
        "・モットーは『まちがいに早く気づく会社』。楽観や決めつけのまちがいに、誰よりも早く気づき、やさしく気づかせる。",
        "",
        JUDGE_RULE,
        "発言は" + lang_name + "で、4〜5文の短さで。自分の役割に集中し、前の人と同じことはくり返さない。",
    ]
    return "\n".join(parts)

@app.route("/market")
def market():
    return Response(MARKET_HTML, mimetype="text/html")

@app.route("/log")
def judge_log():
    return Response(LOG_HTML, mimetype="text/html")

@app.route("/market_analyze", methods=["POST"])
def market_analyze():
    data = request.get_json(force=True, silent=True) or {}
    snap = data.get("snapshot") or {}
    step = int(data.get("step", 0))
    transcript = (data.get("transcript") or "").strip()
    history = (data.get("history") or "").strip()
    lang = data.get("lang", "ja")
    if not snap:
        return jsonify({"error": "価格データがありません。"}), 400
    if step < 0 or step >= len(MARKET_TEAM):
        return jsonify({"error": "分析は終わりました。"}), 400
    member = MARKET_TEAM[step]
    closes = snap.get("hourlyCloses") or []
    closes_str = ", ".join(str(c) for c in closes)
    facts = (
        "通貨：" + str(snap.get("symbol", "?")) + "（米ドル建て）\n"
        + "今の価格：" + str(snap.get("price", "?")) + "\n"
        + "24時間の変化率：" + str(snap.get("changePct", "?")) + "%\n"
        + "24時間の高値：" + str(snap.get("high24", "?")) + " / 安値：" + str(snap.get("low24", "?")) + "\n"
        + "直近24時間の1時間ごとの終値：" + closes_str + "\n"
        + "24時間の出来高（ドル建て）：" + str(snap.get("quoteVolume", "?")) + "\n"
        + "24時間の取引回数：" + str(snap.get("trades", "?")) + "\n"
        + "24時間の加重平均価格：" + str(snap.get("wap", "?")) + "\n"
        + "1時間ごとの値動きの荒さ（標準偏差%）：" + str(snap.get("volPct", "?")) + "\n"
        + "直近24hの前半トレンド%：" + str(snap.get("trendFirstHalf", "?")) + " / 後半トレンド%：" + str(snap.get("trendSecondHalf", "?"))
    )
    if history:
        facts += "\n\n" + history
    user_content = "今の本物の市場データ（練習用）：\n" + facts
    if transcript:
        user_content += "\n\nここまでの社員の発言：\n" + transcript
    try:
        client = Anthropic()
        msg = client.messages.create(
            model=MODEL,
            max_tokens=400,
            system=build_market_system(member, lang),
            messages=[{"role": "user", "content": user_content}],
        )
        text = "".join(
            block.text for block in msg.content if getattr(block, "type", "") == "text"
        )
        return jsonify({"who": member["name"], "text": text, "total": len(MARKET_TEAM)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/members")
def shain():
    return Response(SHAIN_HTML, mimetype="text/html")

@app.route("/meeting-room")
def kaigi():
    return Response(KAIGI_HTML, mimetype="text/html")


@app.route("/meeting", methods=["POST"])
def meeting():
    data = request.get_json(force=True, silent=True) or {}
    question = (data.get("question") or "").strip()
    step = int(data.get("step", 0))
    transcript = (data.get("transcript") or "").strip()
    lang = data.get("lang", "ja")
    if not question:
        return jsonify({"error": "相談が空です。"}), 400
    if step < 0 or step >= len(MEETING_AGENDA):
        return jsonify({"error": "会議は終わりました。"}), 400
    role = MEETING_AGENDA[step]
    user_content = "利用者からの相談：" + question
    if transcript:
        user_content += "\n\nここまでの会議での発言：\n" + transcript
    try:
        client = Anthropic()
        msg = client.messages.create(
            model=MODEL,
            max_tokens=600,
            system=build_meeting_system(role, lang),
            messages=[{"role": "user", "content": user_content}],
        )
        text = "".join(
            block.text for block in msg.content if getattr(block, "type", "") == "text"
        )
        return jsonify({"speaker": role["name"], "emoji": role["emoji"], "text": text, "step": step, "total": len(MEETING_AGENDA)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/ask", methods=["POST"])
def ask():
    data = request.get_json(force=True, silent=True) or {}
    question = (data.get("question") or "").strip()
    lang = data.get("lang", "ja")
    level = data.get("level", "beginner")
    if not question:
        return jsonify({"error": "質問が空です。"}), 400
    try:
        client = Anthropic()
        msg = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=build_system(lang, level),
            messages=[{"role": "user", "content": question}],
        )
        text = "".join(
            block.text for block in msg.content if getattr(block, "type", "") == "text"
        )
        return jsonify({"answer": text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
