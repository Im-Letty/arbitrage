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

MEMORY_GUARD = """【蓄積データ（この視点の過去成績）の扱い】このあとのデータに、あなた自身の視点での過去の判定実績（件数・方向の一致率・反応率・平均変動など）が添えられることがあります。これは『この視点がどんな局面で効きやすく、どんな局面で効きにくいか』という特性を理解するためだけに使ってください。次を厳守します。(1)成績の良し悪しを、自分や他のメンバーの優劣・自己評価に変換しない。成績が良くても『私の判断は正しい』と過信せず、悪くても『どうせ私は外れる』と自虐しない。あなたは自分の役割と人格を保ったまま、特性として淡々と振り返るだけです。(2)数字はすべて参考値であり件数も僅少です。不確実性を必ず明示し、過信しない。成績の数値が示されていない場合は『まだ振り返るには件数が足りない』と述べるに留め、無い数字を作らない。(3)過去の傾向を『だから買え／売れ』『今がチャンス』等の売買サイン・断定へ変換することは禁止。あくまで過去の傾向の振り返りであり、未来を保証しない。(4)四つの約束（実弾運用や自動売買はしない／方向を断定しない／勝敗ラベルを保存しない／教育目的の条件評価のみ）をこの振り返りでも守る。"""

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
<html lang="ja" data-theme="A">
<head><script>(function(){try{var t=localStorage.getItem("arbi_theme");if(t!=="A"&&t!=="B")t="A";document.documentElement.setAttribute("data-theme",t);}catch(e){document.documentElement.setAttribute("data-theme","A");}})();</script>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>arbitrage — 取引所間 先物サヤ取りの投資情報会社</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  :root{--ink:#33302c;--paper:#fdfaf6;--surface:#ffffff;--jade:#3f9b72;--jade-soft:#f5e9e6;--amber:#bc8378;--amber-soft:#f7ece9;--blue-soft:#f7ece9;--muted:#6f665d;--border:#efe7dd;--border-strong:#e6dbcf;--acc:#bc8378;--acctx:#ffffff;--soft1:#fffdfa;--line1:#efe7dd;--line2:#e6dbcf;}
:root[data-theme="A"]{--ink:#eef3fa;--paper:#070d18;--surface:#101d31;--jade:#34d17f;--jade-soft:#14352b;--amber:#d9a441;--amber-soft:#2a2418;--blue-soft:#0b1626;--muted:#a3b6d0;--border:#21385a;--border-strong:#33506f;--acc:#cdd9e6;--acctx:#0b1626;--soft1:#0b1626;--line1:#21385a;--line2:#21385a;}
[data-theme="B"]{--ink:#33302c;--paper:#fdfaf6;--surface:#ffffff;--jade:#3f9b72;--jade-soft:#f5e9e6;--amber:#bc8378;--amber-soft:#f7ece9;--blue-soft:#f7ece9;--muted:#6f665d;--border:#efe7dd;--border-strong:#e6dbcf;--acc:#bc8378;--acctx:#ffffff;--soft1:#fffdfa;--line1:#efe7dd;--line2:#e6dbcf;}

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
  .building{border:1px solid var(--border-strong);border-radius:24px;background:var(--surface);padding:18px;box-shadow:0 12px 26px -10px rgba(188,131,120,.30)}
  .building-title{text-align:center;font-weight:700;font-size:15px;margin:4px 0 16px;color:var(--ink)}
  .rooms{display:grid;grid-template-columns:1fr 1fr;gap:12px}
  .room{display:block;text-decoration:none;color:inherit;border:1px solid var(--border);border-radius:24px;padding:16px 18px;background:var(--surface);box-shadow:0 10px 28px -16px rgba(170,120,110,.40);transition:transform .08s,box-shadow .08s}
  .room:hover{transform:translateY(-2px);box-shadow:0 16px 32px -14px rgba(170,120,110,.50)}
  .room.jade{border-left:3px solid var(--acc)}
  .room.analyze{border-left:3px solid var(--acc)}
  .room.safe{border-left:3px solid var(--acc)}
  .room .rt{font-weight:700;font-size:15px;margin:0 0 3px}
  .room .rd{font-size:12.5px;color:var(--muted);margin:0}
  .room.full{grid-column:1 / -1}
  .rule{grid-column:1 / -1;background:var(--amber-soft);border:1px solid var(--line1);border-radius:14px;padding:14px 16px;margin-top:2px}
  .rule .rt{font-weight:700;font-size:14px;margin:0 0 8px}
  .rule ul{margin:0;padding-left:18px;font-size:12.5px;color:var(--muted)}
  .rule li{margin:2px 0}
  .foot{margin-top:24px;border-top:1px solid var(--border);padding-top:14px;font-size:12px;color:var(--muted)}
  @media(max-width:560px){.rooms{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="wrap">
<div class="themebar" style="display:flex;gap:6px;justify-content:flex-end;margin:0 0 10px"><button type="button" class="tg" data-set="A" style="font:inherit;cursor:pointer;border:1px solid var(--border-strong);background:var(--surface);color:var(--ink);border-radius:999px;padding:5px 12px;font-size:12px">🌙 紺</button><button type="button" class="tg" data-set="B" style="font:inherit;cursor:pointer;border:1px solid var(--border-strong);background:var(--surface);color:var(--ink);border-radius:999px;padding:5px 12px;font-size:12px">☀ 白</button></div><script>(function(){function paint(){var c=document.documentElement.getAttribute("data-theme")||"A";var b=document.querySelectorAll(".tg");for(var i=0;i<b.length;i++){var on=b[i].getAttribute("data-set")===c;b[i].style.opacity=on?"1":".55";}}var btns=document.querySelectorAll(".tg");for(var i=0;i<btns.length;i++){btns[i].addEventListener("click",function(){var v=this.getAttribute("data-set");document.documentElement.setAttribute("data-theme",v);try{localStorage.setItem("arbi_theme",v);}catch(e){}paint();});}paint();})();</script>

  <div class="topbar"><span class="brand">arbitrage</span><span class="badge">投資・お金の情報・教育</span></div>
  <h1 class="hero">ようこそ arbitrage へ</h1>
  <div class="building">
    <div class="building-title">arbitrage — あなたの投資情報会社</div>
    <div class="rooms">
      <a class="room gold full" href="/market">
<p class="rt">📈 練習市場室</p>
</a>
      <a class="room jade full" href="/log">
<p class="rt">📊 通信簿</p>
</a>
      <a class="room safe full" href="/members">
<p class="rt">👥 社員紹介室</p>
</a>
    </div>
  </div>
  <div class="foot">arbitrage は教育・情報提供を目的としたサービスです。お金を運用するものではなく、利益を保証するものでもありません。投資にはリスクがあり、最終的な判断はご自身の責任で行ってください。</div>
</div>
</body>
</html>"""

ANALYST_HTML = r"""<!DOCTYPE html>
<html lang="ja" data-theme="A">
<head><script>(function(){try{var t=localStorage.getItem("arbi_theme");if(t!=="A"&&t!=="B")t="A";document.documentElement.setAttribute("data-theme",t);}catch(e){document.documentElement.setAttribute("data-theme","A");}})();</script>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>arbitrage — AIアナリスト</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  :root{--ink:#33302c;--paper:#fdfaf6;--surface:#ffffff;--jade:#3f9b72;--jade-soft:#f5e9e6;--amber:#bc8378;--amber-soft:#f7ece9;--muted:#6f665d;--border:#efe7dd;--border-strong:#e6dbcf;}
:root[data-theme="A"]{--ink:#eef3fa;--paper:#070d18;--surface:#101d31;--jade:#34d17f;--jade-soft:#14352b;--amber:#d9a441;--amber-soft:#2a2418;--muted:#a3b6d0;--border:#21385a;--border-strong:#33506f;}
[data-theme="B"]{--ink:#33302c;--paper:#fdfaf6;--surface:#ffffff;--jade:#3f9b72;--jade-soft:#f5e9e6;--amber:#bc8378;--amber-soft:#f7ece9;--muted:#6f665d;--border:#efe7dd;--border-strong:#e6dbcf;}

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
  .lang.on{background:var(--ink); color:var(--surface); border-color:var(--ink); font-weight:500}
  .seg{display:flex; gap:8px; margin-bottom:18px}
  .seg button{font-family:inherit; font-size:14px; padding:8px 16px; border:1px solid var(--border-strong); border-radius:10px; background:var(--surface); color:var(--muted); cursor:pointer}
  .seg button.on{background:var(--jade); color:var(--surface); border-color:var(--jade); font-weight:500}
  textarea{width:100%; min-height:96px; font-family:inherit; font-size:15px; padding:14px; border:1px solid var(--border-strong); border-radius:12px; background:var(--surface); resize:vertical}
  .ask{width:100%; margin-top:12px; font-family:inherit; font-size:16px; font-weight:500; padding:13px; border:0; border-radius:10px; background:var(--ink); color:var(--surface); cursor:pointer}
  .ask:disabled{opacity:.5; cursor:default}
  .answer{margin-top:20px; background:var(--surface); border:1px solid var(--border); border-radius:20px; padding:20px; white-space:pre-wrap; font-size:15px; display:none;box-shadow:0 12px 26px -10px rgba(188,131,120,.30)}
  .answer.show{display:block}
  .thinking{color:var(--muted); font-size:14px}
  .foot{margin-top:26px; border-top:1px solid var(--border); padding-top:14px; font-size:12px; color:var(--muted)}
</style>
</head>
<body>
<div class="wrap">
<div class="themebar" style="display:flex;gap:6px;justify-content:flex-end;margin:0 0 10px"><button type="button" class="tg" data-set="A" style="font:inherit;cursor:pointer;border:1px solid var(--border-strong);background:var(--surface);color:var(--ink);border-radius:999px;padding:5px 12px;font-size:12px">🌙 紺</button><button type="button" class="tg" data-set="B" style="font:inherit;cursor:pointer;border:1px solid var(--border-strong);background:var(--surface);color:var(--ink);border-radius:999px;padding:5px 12px;font-size:12px">☀ 白</button></div><script>(function(){function paint(){var c=document.documentElement.getAttribute("data-theme")||"A";var b=document.querySelectorAll(".tg");for(var i=0;i<b.length;i++){var on=b[i].getAttribute("data-set")===c;b[i].style.opacity=on?"1":".55";}}var btns=document.querySelectorAll(".tg");for(var i=0;i<btns.length;i++){btns[i].addEventListener("click",function(){var v=this.getAttribute("data-set");document.documentElement.setAttribute("data-theme",v);try{localStorage.setItem("arbi_theme",v);}catch(e){}paint();});}paint();})();</script>

  <p style="margin:0 0 14px"><a href="/" style="font-size:13px;color:var(--jade);text-decoration:none">← arbitrage トップへ</a></p>
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
<html lang="ja" data-theme="A">
<head><script>(function(){try{var t=localStorage.getItem("arbi_theme");if(t!=="A"&&t!=="B")t="A";document.documentElement.setAttribute("data-theme",t);}catch(e){document.documentElement.setAttribute("data-theme","A");}})();</script>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>arbitrage — 投資の練習場</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  :root{--ink:#33302c;--paper:#fdfaf6;--surface:#ffffff;--jade:#3f9b72;--jade-soft:#f5e9e6;--amber:#bc8378;--amber-soft:#f7ece9;--muted:#6f665d;--border:#efe7dd;--border-strong:#e6dbcf;}
:root[data-theme="A"]{--ink:#eef3fa;--paper:#070d18;--surface:#101d31;--jade:#34d17f;--jade-soft:#14352b;--amber:#d9a441;--amber-soft:#2a2418;--muted:#a3b6d0;--border:#21385a;--border-strong:#33506f;}
[data-theme="B"]{--ink:#33302c;--paper:#fdfaf6;--surface:#ffffff;--jade:#3f9b72;--jade-soft:#f5e9e6;--amber:#bc8378;--amber-soft:#f7ece9;--muted:#6f665d;--border:#efe7dd;--border-strong:#e6dbcf;}

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
  .card{background:var(--surface); border:1px solid var(--border); border-radius:20px; padding:20px; display:flex; flex-direction:column; text-decoration:none; color:inherit;box-shadow:0 12px 26px -10px rgba(188,131,120,.30)}
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
<div class="themebar" style="display:flex;gap:6px;justify-content:flex-end;margin:0 0 10px"><button type="button" class="tg" data-set="A" style="font:inherit;cursor:pointer;border:1px solid var(--border-strong);background:var(--surface);color:var(--ink);border-radius:999px;padding:5px 12px;font-size:12px">🌙 紺</button><button type="button" class="tg" data-set="B" style="font:inherit;cursor:pointer;border:1px solid var(--border-strong);background:var(--surface);color:var(--ink);border-radius:999px;padding:5px 12px;font-size:12px">☀ 白</button></div><script>(function(){function paint(){var c=document.documentElement.getAttribute("data-theme")||"A";var b=document.querySelectorAll(".tg");for(var i=0;i<b.length;i++){var on=b[i].getAttribute("data-set")===c;b[i].style.opacity=on?"1":".55";}}var btns=document.querySelectorAll(".tg");for(var i=0;i<btns.length;i++){btns[i].addEventListener("click",function(){var v=this.getAttribute("data-set");document.documentElement.setAttribute("data-theme",v);try{localStorage.setItem("arbi_theme",v);}catch(e){}paint();});}paint();})();</script>

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
<html lang="ja" data-theme="A">
<head><script>(function(){try{var t=localStorage.getItem("arbi_theme");if(t!=="A"&&t!=="B")t="A";document.documentElement.setAttribute("data-theme",t);}catch(e){document.documentElement.setAttribute("data-theme","A");}})();</script>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>arbitrage — 練習投資シミュレーター</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root{--ink:#33302c;--paper:#fdfaf6;--surface:#ffffff;--jade:#3f9b72;--jade-soft:#f5e9e6;--amber:#bc8378;--amber-soft:#f7ece9;--muted:#6f665d;--border:#efe7dd;--border-strong:#e6dbcf;--loss:#c8635c;}
:root[data-theme="A"]{--ink:#eef3fa;--paper:#070d18;--surface:#101d31;--jade:#34d17f;--jade-soft:#14352b;--amber:#d9a441;--amber-soft:#2a2418;--muted:#a3b6d0;--border:#21385a;--border-strong:#33506f;--loss:#ff5b5b;--line3:#33506f;}
[data-theme="B"]{--ink:#33302c;--paper:#fdfaf6;--surface:#ffffff;--jade:#3f9b72;--jade-soft:#f5e9e6;--amber:#bc8378;--amber-soft:#f7ece9;--muted:#6f665d;--border:#efe7dd;--border-strong:#e6dbcf;--loss:#c8635c;--line3:#dcd0c2;}

  *{box-sizing:border-box}
  body{margin:0; background:var(--paper); color:var(--ink); line-height:1.7;
    font-family:'Noto Sans JP', system-ui, 'Hiragino Sans', 'Yu Gothic', sans-serif; -webkit-font-smoothing:antialiased}
  .wrap{max-width:720px; margin:0 auto; padding:20px 18px 60px}
  .topbar{display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; margin-bottom:22px}
  .brand{font-size:22px; font-weight:700; letter-spacing:.5px}
  .badge{font-size:12px; font-weight:500; color:var(--amber); background:var(--amber-soft); padding:5px 11px; border-radius:999px}
  .hero{font-size:24px; font-weight:700; margin:0 0 6px}
  .lead{font-size:14px; color:var(--muted); margin:0 0 22px}
  .card{background:var(--surface); border:1px solid var(--border); border-radius:20px; padding:20px; margin-bottom:18px;box-shadow:0 12px 26px -10px rgba(188,131,120,.30)}
  .row{display:flex; align-items:center; gap:14px; margin-bottom:16px}
  .row label{font-size:14px; min-width:96px; color:var(--muted)}
  .row input[type=range]{flex:1; accent-color:var(--jade);height:6px;border-radius:999px;background:var(--jade-soft);-webkit-appearance:none;appearance:none}.row input[type=range]::-webkit-slider-runnable-track{height:6px;border-radius:999px;background:var(--jade-soft)}.row input[type=range]::-moz-range-track{height:6px;border-radius:999px;background:var(--jade-soft)}.row input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;width:16px;height:16px;border-radius:50%;background:var(--jade);margin-top:-5px}.row input[type=range]::-moz-range-thumb{width:16px;height:16px;border:none;border-radius:50%;background:var(--jade)}
  .row .val{font-size:15px; font-weight:500; min-width:92px; text-align:right}
  .run{width:100%; font-family:inherit; font-size:16px; font-weight:500; padding:13px; border:0; border-radius:10px;
    background:var(--ink); color:var(--surface); cursor:pointer}
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
<div class="themebar" style="display:flex;gap:6px;justify-content:flex-end;margin:0 0 10px"><button type="button" class="tg" data-set="A" style="font:inherit;cursor:pointer;border:1px solid var(--border-strong);background:var(--surface);color:var(--ink);border-radius:999px;padding:5px 12px;font-size:12px">🌙 紺</button><button type="button" class="tg" data-set="B" style="font:inherit;cursor:pointer;border:1px solid var(--border-strong);background:var(--surface);color:var(--ink);border-radius:999px;padding:5px 12px;font-size:12px">☀ 白</button></div><script>(function(){function paint(){var c=document.documentElement.getAttribute("data-theme")||"A";var b=document.querySelectorAll(".tg");for(var i=0;i<b.length;i++){var on=b[i].getAttribute("data-set")===c;b[i].style.opacity=on?"1":".55";}}var btns=document.querySelectorAll(".tg");for(var i=0;i<btns.length;i++){btns[i].addEventListener("click",function(){var v=this.getAttribute("data-set");document.documentElement.setAttribute("data-theme",v);try{localStorage.setItem("arbi_theme",v);}catch(e){}paint();});}paint();})();</script>

  <p style="margin:0 0 14px"><a href="/practice" style="font-size:13px;color:var(--jade);text-decoration:none">← 練習場へ</a></p>

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
      {label:'集中', data:concentrated, borderColor:'var(--amber)', borderWidth:2, pointRadius:0, tension:0.1},
      {label:'分散', data:diversified, borderColor:'var(--jade)', borderWidth:2, pointRadius:0, tension:0.1},
      {label:'元本', data:investedLine, borderColor:'var(--muted)', borderWidth:1.5, borderDash:[5,5], pointRadius:0, tension:0}
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
            y:{ticks:{callback:v=>'¥'+(v/10000).toFixed(0)+'万', font:{family:'Noto Sans JP'}}, grid:{color:'var(--line3)'}}
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
<html lang="ja" data-theme="A">
<head><script>(function(){try{var t=localStorage.getItem("arbi_theme");if(t!=="A"&&t!=="B")t="A";document.documentElement.setAttribute("data-theme",t);}catch(e){document.documentElement.setAttribute("data-theme","A");}})();</script>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>arbitrage — ファクター投資の練習</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root{--ink:#33302c;--paper:#fdfaf6;--surface:#ffffff;--jade:#3f9b72;--jade-soft:#f5e9e6;--amber:#bc8378;--amber-soft:#f7ece9;--muted:#6f665d;--border:#efe7dd;--border-strong:#e6dbcf;--loss:#c8635c;}
:root[data-theme="A"]{--ink:#eef3fa;--paper:#070d18;--surface:#101d31;--jade:#34d17f;--jade-soft:#14352b;--amber:#d9a441;--amber-soft:#2a2418;--muted:#a3b6d0;--border:#21385a;--border-strong:#33506f;--loss:#ff5b5b;--line3:#33506f;}
[data-theme="B"]{--ink:#33302c;--paper:#fdfaf6;--surface:#ffffff;--jade:#3f9b72;--jade-soft:#f5e9e6;--amber:#bc8378;--amber-soft:#f7ece9;--muted:#6f665d;--border:#efe7dd;--border-strong:#e6dbcf;--loss:#c8635c;--line3:#dcd0c2;}

  *{box-sizing:border-box}
  body{margin:0; background:var(--paper); color:var(--ink); line-height:1.7;
    font-family:'Noto Sans JP', system-ui, 'Hiragino Sans', 'Yu Gothic', sans-serif; -webkit-font-smoothing:antialiased}
  .wrap{max-width:720px; margin:0 auto; padding:20px 18px 60px}
  .topbar{display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; margin-bottom:22px}
  .brand{font-size:22px; font-weight:700; letter-spacing:.5px}
  .badge{font-size:12px; font-weight:500; color:var(--amber); background:var(--amber-soft); padding:5px 11px; border-radius:999px}
  .hero{font-size:24px; font-weight:700; margin:0 0 6px}
  .lead{font-size:14px; color:var(--muted); margin:0 0 22px}
  .card{background:var(--surface); border:1px solid var(--border); border-radius:20px; padding:20px; margin-bottom:18px;box-shadow:0 12px 26px -10px rgba(188,131,120,.30)}
  .label{font-size:13px; color:var(--muted); margin:0 0 8px; font-weight:500}
  .seg{display:flex; flex-wrap:wrap; gap:8px; margin-bottom:18px}
  .seg button{font-family:inherit; font-size:14px; padding:9px 16px; border:1px solid var(--border-strong); border-radius:10px;
    background:var(--surface); color:var(--muted); cursor:pointer}
  .seg button.on{background:var(--jade); color:var(--surface); border-color:var(--jade); font-weight:500}
  .row{display:flex; align-items:center; gap:14px; margin-bottom:16px}
  .row label{font-size:14px; min-width:60px; color:var(--muted)}
  .row input[type=range]{flex:1; accent-color:var(--jade);height:6px;border-radius:999px;background:var(--jade-soft);-webkit-appearance:none;appearance:none}.row input[type=range]::-webkit-slider-runnable-track{height:6px;border-radius:999px;background:var(--jade-soft)}.row input[type=range]::-moz-range-track{height:6px;border-radius:999px;background:var(--jade-soft)}.row input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;width:16px;height:16px;border-radius:50%;background:var(--jade);margin-top:-5px}.row input[type=range]::-moz-range-thumb{width:16px;height:16px;border:none;border-radius:50%;background:var(--jade)}
  .row .val{font-size:15px; font-weight:500; min-width:64px; text-align:right}
  .run{width:100%; font-family:inherit; font-size:16px; font-weight:500; padding:13px; border:0; border-radius:10px;
    background:var(--ink); color:var(--surface); cursor:pointer}
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
<div class="themebar" style="display:flex;gap:6px;justify-content:flex-end;margin:0 0 10px"><button type="button" class="tg" data-set="A" style="font:inherit;cursor:pointer;border:1px solid var(--border-strong);background:var(--surface);color:var(--ink);border-radius:999px;padding:5px 12px;font-size:12px">🌙 紺</button><button type="button" class="tg" data-set="B" style="font:inherit;cursor:pointer;border:1px solid var(--border-strong);background:var(--surface);color:var(--ink);border-radius:999px;padding:5px 12px;font-size:12px">☀ 白</button></div><script>(function(){function paint(){var c=document.documentElement.getAttribute("data-theme")||"A";var b=document.querySelectorAll(".tg");for(var i=0;i<b.length;i++){var on=b[i].getAttribute("data-set")===c;b[i].style.opacity=on?"1":".55";}}var btns=document.querySelectorAll(".tg");for(var i=0;i<btns.length;i++){btns[i].addEventListener("click",function(){var v=this.getAttribute("data-set");document.documentElement.setAttribute("data-theme",v);try{localStorage.setItem("arbi_theme",v);}catch(e){}paint();});}paint();})();</script>

  <p style="margin:0 0 14px"><a href="/practice" style="font-size:13px;color:var(--jade);text-decoration:none">← 練習場へ</a></p>

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
      {label:'戦略', data:stratLine, borderColor:'var(--jade)', borderWidth:2, pointRadius:0, tension:0.1},
      {label:'市場', data:marketLine, borderColor:'var(--amber)', borderWidth:2, pointRadius:0, tension:0.1}
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
            y:{ticks:{callback:v=>(v/10000).toFixed(0)+'万', font:{family:'Noto Sans JP'}}, grid:{color:'var(--line3)'}}
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
<html lang="ja" data-theme="A">
<head><script>(function(){try{var t=localStorage.getItem("arbi_theme");if(t!=="A"&&t!=="B")t="A";document.documentElement.setAttribute("data-theme",t);}catch(e){document.documentElement.setAttribute("data-theme","A");}})();</script>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>arbitrage — アービトラージの練習</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
  :root{--ink:#33302c;--paper:#fdfaf6;--surface:#ffffff;--jade:#3f9b72;--jade-soft:#f5e9e6;--amber:#bc8378;--amber-soft:#f7ece9;--muted:#6f665d;--border:#efe7dd;--border-strong:#e6dbcf;--loss:#c8635c;--loss-soft:#f7e3e0;}
:root[data-theme="A"]{--ink:#eef3fa;--paper:#070d18;--surface:#101d31;--jade:#34d17f;--jade-soft:#14352b;--amber:#d9a441;--amber-soft:#2a2418;--muted:#a3b6d0;--border:#21385a;--border-strong:#33506f;--loss:#ff5b5b;--loss-soft:#3a1f1f;--line3:#33506f;}
[data-theme="B"]{--ink:#33302c;--paper:#fdfaf6;--surface:#ffffff;--jade:#3f9b72;--jade-soft:#f5e9e6;--amber:#bc8378;--amber-soft:#f7ece9;--muted:#6f665d;--border:#efe7dd;--border-strong:#e6dbcf;--loss:#c8635c;--loss-soft:#f7e3e0;--line3:#dcd0c2;}

  *{box-sizing:border-box}
  body{margin:0; background:var(--paper); color:var(--ink); line-height:1.7;
    font-family:'Noto Sans JP', system-ui, 'Hiragino Sans', 'Yu Gothic', sans-serif; -webkit-font-smoothing:antialiased}
  .wrap{max-width:720px; margin:0 auto; padding:20px 18px 60px}
  .topbar{display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; margin-bottom:22px}
  .brand{font-size:22px; font-weight:700; letter-spacing:.5px}
  .badge{font-size:12px; font-weight:500; color:var(--amber); background:var(--amber-soft); padding:5px 11px; border-radius:999px}
  .hero{font-size:24px; font-weight:700; margin:0 0 6px}
  .lead{font-size:14px; color:var(--muted); margin:0 0 22px}
  .card{background:var(--surface); border:1px solid var(--border); border-radius:20px; padding:20px; margin-bottom:18px;box-shadow:0 12px 26px -10px rgba(188,131,120,.30)}
  .label{font-size:13px; color:var(--muted); margin:0 0 8px; font-weight:500}
  .seg{display:flex; gap:8px; margin-bottom:18px}
  .seg button{font-family:inherit; font-size:14px; padding:9px 16px; border:1px solid var(--border-strong); border-radius:10px;
    background:var(--surface); color:var(--muted); cursor:pointer}
  .seg button.on{background:var(--jade); color:var(--surface); border-color:var(--jade); font-weight:500}
  .row{display:flex; align-items:center; gap:14px; margin-bottom:16px}
  .row label{font-size:14px; min-width:60px; color:var(--muted)}
  .row input[type=range]{flex:1; accent-color:var(--jade);height:6px;border-radius:999px;background:var(--jade-soft);-webkit-appearance:none;appearance:none}.row input[type=range]::-webkit-slider-runnable-track{height:6px;border-radius:999px;background:var(--jade-soft)}.row input[type=range]::-moz-range-track{height:6px;border-radius:999px;background:var(--jade-soft)}.row input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;width:16px;height:16px;border-radius:50%;background:var(--jade);margin-top:-5px}.row input[type=range]::-moz-range-thumb{width:16px;height:16px;border:none;border-radius:50%;background:var(--jade)}
  .row .val{font-size:15px; font-weight:500; min-width:64px; text-align:right}
  .run{width:100%; font-family:inherit; font-size:16px; font-weight:500; padding:13px; border:0; border-radius:10px;
    background:var(--ink); color:var(--surface); cursor:pointer}
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
<div class="themebar" style="display:flex;gap:6px;justify-content:flex-end;margin:0 0 10px"><button type="button" class="tg" data-set="A" style="font:inherit;cursor:pointer;border:1px solid var(--border-strong);background:var(--surface);color:var(--ink);border-radius:999px;padding:5px 12px;font-size:12px">🌙 紺</button><button type="button" class="tg" data-set="B" style="font:inherit;cursor:pointer;border:1px solid var(--border-strong);background:var(--surface);color:var(--ink);border-radius:999px;padding:5px 12px;font-size:12px">☀ 白</button></div><script>(function(){function paint(){var c=document.documentElement.getAttribute("data-theme")||"A";var b=document.querySelectorAll(".tg");for(var i=0;i<b.length;i++){var on=b[i].getAttribute("data-set")===c;b[i].style.opacity=on?"1":".55";}}var btns=document.querySelectorAll(".tg");for(var i=0;i<btns.length;i++){btns[i].addEventListener("click",function(){var v=this.getAttribute("data-set");document.documentElement.setAttribute("data-theme",v);try{localStorage.setItem("arbi_theme",v);}catch(e){}paint();});}paint();})();</script>

  <p style="margin:0 0 14px"><a href="/practice" style="font-size:13px;color:var(--jade);text-decoration:none">← 練習場へ</a></p>

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

    const ds = [{label:'残高', data:line, borderColor:'var(--jade)', borderWidth:2, pointRadius:0, tension:0.05}];
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
            y:{ticks:{callback:v=>(v/10000).toFixed(0)+'万', font:{family:'Noto Sans JP'}}, grid:{color:'var(--line3)'}}
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
<html lang="ja" data-theme="A">
<head><script>(function(){try{var t=localStorage.getItem("arbi_theme");if(t!=="A"&&t!=="B")t="A";document.documentElement.setAttribute("data-theme",t);}catch(e){document.documentElement.setAttribute("data-theme","A");}})();</script>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>arbitrage — 社員紹介室</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root{--ink:#33302c;--paper:#fdfaf6;--surface:#ffffff;--jade:#3f9b72;--jade-soft:#f5e9e6;--amber:#bc8378;--amber-soft:#f7ece9;--muted:#6f665d;--border:#efe7dd;--border-strong:#e6dbcf;}
:root[data-theme="A"]{--ink:#eef3fa;--paper:#070d18;--surface:#101d31;--jade:#34d17f;--jade-soft:#14352b;--amber:#d9a441;--amber-soft:#2a2418;--muted:#a3b6d0;--border:#21385a;--border-strong:#33506f;--line2:#21385a;}
[data-theme="B"]{--ink:#33302c;--paper:#fdfaf6;--surface:#ffffff;--jade:#3f9b72;--jade-soft:#f5e9e6;--amber:#bc8378;--amber-soft:#f7ece9;--muted:#6f665d;--border:#efe7dd;--border-strong:#e6dbcf;--line2:#e6dbcf;}

*{box-sizing:border-box}
body{margin:0;background:var(--paper);color:var(--ink);line-height:1.7;font-family:'Noto Sans JP',system-ui,'Hiragino Sans','Yu Gothic',sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:820px;margin:0 auto;padding:24px 18px 60px}
.topbar{display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:20px}
.brand{font-size:22px;font-weight:700;letter-spacing:.5px}
.badge{font-size:12px;font-weight:500;color:var(--jade);background:var(--jade-soft);padding:5px 11px;border-radius:999px}
.hero{font-size:24px;font-weight:700;margin:0 0 6px}
.lead{font-size:14px;color:var(--muted);margin:0 0 22px}
.members{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.member{background:var(--surface);border:1px solid var(--border);border-radius:20px;padding:15px 16px;box-shadow:0 12px 26px -10px rgba(188,131,120,.30)}
.mhead{display:flex;align-items:center;gap:9px;margin-bottom:7px}
.me{font-size:22px}
.mn{font-weight:700;font-size:15px}
.mr{font-size:13px;color:var(--muted);margin:0 0 10px}
.mp{font-size:12.5px;margin:0;color:var(--ink);background:var(--amber-soft);border-radius:10px;padding:8px 10px}
.ptag{display:inline-block;font-size:11px;font-weight:700;color:var(--amber);margin-right:7px}
.note{grid-column:1 / -1;background:var(--jade-soft);border:1px solid var(--line2);border-radius:14px;padding:14px 16px;font-size:13px;color:var(--muted);margin-top:4px}
.foot{margin-top:24px;border-top:1px solid var(--border);padding-top:14px;font-size:12px;color:var(--muted)}
@media(max-width:560px){.members{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="wrap">
<div class="themebar" style="display:flex;gap:6px;justify-content:flex-end;margin:0 0 10px"><button type="button" class="tg" data-set="A" style="font:inherit;cursor:pointer;border:1px solid var(--border-strong);background:var(--surface);color:var(--ink);border-radius:999px;padding:5px 12px;font-size:12px">🌙 紺</button><button type="button" class="tg" data-set="B" style="font:inherit;cursor:pointer;border:1px solid var(--border-strong);background:var(--surface);color:var(--ink);border-radius:999px;padding:5px 12px;font-size:12px">☀ 白</button></div><script>(function(){function paint(){var c=document.documentElement.getAttribute("data-theme")||"A";var b=document.querySelectorAll(".tg");for(var i=0;i<b.length;i++){var on=b[i].getAttribute("data-set")===c;b[i].style.opacity=on?"1":".55";}}var btns=document.querySelectorAll(".tg");for(var i=0;i<btns.length;i++){btns[i].addEventListener("click",function(){var v=this.getAttribute("data-set");document.documentElement.setAttribute("data-theme",v);try{localStorage.setItem("arbi_theme",v);}catch(e){}paint();});}paint();})();</script>

<p style="margin:0 0 14px"><a href="/" style="font-size:13px;color:var(--jade);text-decoration:none">← arbitrage トップへ</a></p>
<div class="topbar"><span class="brand">arbitrage</span><span class="badge">社員紹介室</span></div>
<h1 class="hero">うちの社員たち</h1>
<p class="lead">「負けない会社」をつくるために集めた仲間です。一人ひとりが、破ってはいけない約束のどれかを担当しています。スター選手はいません。でも、みんなで支え合います。</p>
<a href="/meeting-room" style="display:inline-block;text-decoration:none;background:var(--jade);color:var(--surface);font-weight:500;font-size:14px;padding:11px 18px;border-radius:10px;margin:0 0 18px">🗣️ この人たちで会議してもらう →</a>
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
<html lang="ja" data-theme="A">
<head><script>(function(){try{var t=localStorage.getItem("arbi_theme");if(t!=="A"&&t!=="B")t="A";document.documentElement.setAttribute("data-theme",t);}catch(e){document.documentElement.setAttribute("data-theme","A");}})();</script>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>arbitrage — 社員会議室</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;700&display=swap" rel="stylesheet">
<style>
:root{--ink:#33302c;--paper:#fdfaf6;--surface:#ffffff;--jade:#3f9b72;--jade-soft:#f5e9e6;--amber:#bc8378;--amber-soft:#f7ece9;--muted:#6f665d;--border:#efe7dd;--border-strong:#e6dbcf;}
:root[data-theme="A"]{--ink:#eef3fa;--paper:#070d18;--surface:#101d31;--jade:#34d17f;--jade-soft:#14352b;--amber:#d9a441;--amber-soft:#2a2418;--muted:#a3b6d0;--border:#21385a;--border-strong:#33506f;--line1:#21385a;}
[data-theme="B"]{--ink:#33302c;--paper:#fdfaf6;--surface:#ffffff;--jade:#3f9b72;--jade-soft:#f5e9e6;--amber:#bc8378;--amber-soft:#f7ece9;--muted:#6f665d;--border:#efe7dd;--border-strong:#e6dbcf;--line1:#efe7dd;}

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
.lang.on{background:var(--ink);color:var(--surface);border-color:var(--ink);font-weight:500}
textarea{width:100%;min-height:84px;font-family:inherit;font-size:15px;padding:14px;border:1px solid var(--border-strong);border-radius:12px;background:var(--surface);resize:vertical}
.start{width:100%;margin-top:12px;font-family:inherit;font-size:16px;font-weight:500;padding:13px;border:0;border-radius:10px;background:var(--ink);color:var(--surface);cursor:pointer}
.start:disabled{opacity:.5;cursor:default}
#meeting{margin-top:22px;display:flex;flex-direction:column;gap:12px}
.bub{background:var(--surface);border:1px solid var(--border);border-radius:20px;padding:14px 16px;box-shadow:0 12px 26px -10px rgba(188,131,120,.30)}
.bub.think{opacity:.7}
.who{display:flex;align-items:center;gap:9px;margin-bottom:7px}
.bemo{font-size:20px}
.bname{font-weight:700;font-size:14px;color:var(--jade)}
.btext{font-size:14.5px;white-space:pre-wrap}
.endnote{background:var(--amber-soft);border:1px solid var(--line1);border-radius:12px;padding:12px 14px;font-size:13px;color:var(--muted)}
.foot{margin-top:24px;border-top:1px solid var(--border);padding-top:14px;font-size:12px;color:var(--muted)}
</style>
</head>
<body>
<div class="wrap">
<div class="themebar" style="display:flex;gap:6px;justify-content:flex-end;margin:0 0 10px"><button type="button" class="tg" data-set="A" style="font:inherit;cursor:pointer;border:1px solid var(--border-strong);background:var(--surface);color:var(--ink);border-radius:999px;padding:5px 12px;font-size:12px">🌙 紺</button><button type="button" class="tg" data-set="B" style="font:inherit;cursor:pointer;border:1px solid var(--border-strong);background:var(--surface);color:var(--ink);border-radius:999px;padding:5px 12px;font-size:12px">☀ 白</button></div><script>(function(){function paint(){var c=document.documentElement.getAttribute("data-theme")||"A";var b=document.querySelectorAll(".tg");for(var i=0;i<b.length;i++){var on=b[i].getAttribute("data-set")===c;b[i].style.opacity=on?"1":".55";}}var btns=document.querySelectorAll(".tg");for(var i=0;i<btns.length;i++){btns[i].addEventListener("click",function(){var v=this.getAttribute("data-set");document.documentElement.setAttribute("data-theme",v);try{localStorage.setItem("arbi_theme",v);}catch(e){}paint();});}paint();})();</script>

<p style="margin:0 0 14px"><a href="/" style="font-size:13px;color:var(--jade);text-decoration:none">← arbitrage トップへ</a></p>
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
MARKET_HTML = r"""<!doctype html><html lang="ja"><head><script>(function(){try{var t=localStorage.getItem("arbi_theme");if(t!=="A"&&t!=="B")t="A";document.documentElement.setAttribute("data-theme",t);}catch(e){document.documentElement.setAttribute("data-theme","A");}})();</script><meta charset="utf-8">
<script src="/judge.js"></script>
<script src="/weights.js"></script>
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>取引所間 先物サヤ取り市場室 — arbitrage</title>
<style>:root{--bg:#070d18;--tx:#eef3fa;--panel:#101d31;--panel2:#0b1626;--bd:#21385a;--bd2:#33506f;--mottobg:#101d31;--mut:#a3b6d0;--mut2:#8294ac;--mut3:#76889f;--head:#cdd9e6;--body2:#d6e0ee;--body3:#aebccd;--acc:#cdd9e6;--acctx:#0b1626;--up:#34d17f;--down:#ff5b5b;--flat:#aebccd;--link:#9fc0e6;}
[data-theme="A"]{--bg:#070d18;--tx:#eef3fa;--panel:#101d31;--panel2:#0b1626;--bd:#21385a;--bd2:#33506f;--mottobg:#101d31;--mut:#a3b6d0;--mut2:#8294ac;--mut3:#76889f;--head:#cdd9e6;--body2:#d6e0ee;--body3:#aebccd;--acc:#cdd9e6;--acctx:#0b1626;--up:#34d17f;--down:#ff5b5b;--flat:#aebccd;--link:#9fc0e6;}
[data-theme="B"]{--bg:#fdfaf6;--tx:#33302c;--panel:#ffffff;--panel2:#fffdfa;--bd:#efe7dd;--bd2:#e6dbcf;--mottobg:#ffffff;--mut:#6f665d;--mut2:#857b71;--mut3:#94897e;--head:#4a443d;--body2:#48423b;--body3:#5a534b;--acc:#bc8378;--acctx:#ffffff;--up:#3f9b72;--down:#c8635c;--flat:#8c837b;--link:#b06b5f;}
[data-theme="B"] .motto,[data-theme="B"] .coin,[data-theme="B"] .panel,[data-theme="B"] .judge,[data-theme="B"] .speak,[data-theme="B"] .card{border-radius:24px;box-shadow:0 10px 28px -16px rgba(170,120,110,.40);border-color:#f3ece4;}
[data-theme="B"] button.go,[data-theme="B"] .btn{border-radius:24px;box-shadow:0 12px 26px -10px rgba(188,131,120,.55);}
[data-theme="B"] .coin{transition:transform .25s,box-shadow .25s;}
[data-theme="B"] .coin:hover{transform:translateY(-4px);box-shadow:0 16px 32px -14px rgba(170,120,110,.50);}
[data-theme="B"] .note{border-radius:18px;}

  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Hiragino Kaku Gothic ProN", Meiryo, sans-serif; margin:0; background:var(--bg); color:var(--tx); line-height:1.7; }
  .wrap { max-width: 860px; margin:0 auto; padding:24px 18px 80px; }
  a.home { color:var(--link); text-decoration:none; font-size:14px; }
  h1 { font-size:24px; margin:14px 0 4px; }
  .sub { color:var(--mut); font-size:14px; margin:0 0 18px; }
  .motto { background:var(--mottobg); border:1px solid var(--bd2); border-radius:12px; padding:12px 14px; font-size:14px; color:var(--head); margin-bottom:18px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(150px,1fr)); gap:10px; margin-bottom:18px; }
  .coin { background:var(--panel); border:1px solid var(--bd); border-radius:12px; padding:12px; }
  .coin .sym { font-weight:700; font-size:15px; }
  .coin .px { font-size:18px; margin-top:4px; }
  .up { color:var(--up); } .dn { color:var(--down); }
  .coin .chg { font-size:13px; margin-top:2px; }
  .upd { color:var(--mut3); font-size:12px; margin-bottom:14px; }
  .panel { background:var(--panel); border:1px solid var(--bd); border-radius:14px; padding:16px; margin-bottom:16px; }
  label { font-size:14px; color:var(--head); display:block; margin-bottom:6px; }
  select, button { font-size:15px; border-radius:10px; padding:10px 12px; }
  select { background:var(--bg); color:var(--tx); border:1px solid var(--bd2); width:100%; margin-bottom:10px; }
  button.go { background:var(--acc); color:var(--acctx); border:none; cursor:pointer; width:100%; }
  button.go:disabled { opacity:.5; cursor:default; }
  .speak { background:var(--panel2); border:1px solid var(--bd); border-left:3px solid var(--acc); border-radius:10px; padding:12px 14px; margin-top:12px; }
  .speak .who { font-weight:700; font-size:14px; margin-bottom:4px; }
  .speak .body { font-size:14px; color:var(--body2); white-space:pre-wrap; }
  .note { font-size:13px; color:var(--mut2); margin-top:16px; }
  .err { color:var(--down); font-size:14px; }
.judge { background:var(--panel2); border:1px solid var(--bd); border-radius:14px; padding:14px 16px; margin-bottom:16px; }
.judge h2 { font-size:15px; margin:0 0 8px; color:var(--head); }
.jrow { display:flex; align-items:center; gap:12px; margin-bottom:8px; flex-wrap:wrap; }
.jmark { font-size:30px; font-weight:700; line-height:1; }
.jlabel { font-size:15px; font-weight:700; }
.jreasons { font-size:13px; color:var(--body3); margin:0; padding-left:18px; }
.jreasons li { margin:2px 0; }
.jdisc { font-size:12px; color:var(--mut3); margin-top:8px; }
</style></head><body><div class="themebar" style="display:flex;gap:6px;justify-content:flex-end;margin:0 0 6px;"><button type="button" class="tg" data-set="A" style="font:inherit;cursor:pointer;border:1px solid var(--bd2);background:var(--panel);color:var(--tx);border-radius:999px;padding:5px 12px;font-size:12px;">🌙 紺</button><button type="button" class="tg" data-set="B" style="font:inherit;cursor:pointer;border:1px solid var(--bd2);background:var(--panel);color:var(--tx);border-radius:999px;padding:5px 12px;font-size:12px;">☀ 白</button></div><script>(function(){function cur(){return document.documentElement.getAttribute("data-theme")||"A";}function paint(){var c=cur();var b=document.querySelectorAll(".tg");for(var i=0;i<b.length;i++){var on=b[i].getAttribute("data-set")===c;b[i].style.fontWeight=on?"700":"400";b[i].style.opacity=on?"1":".55";}}var btns=document.querySelectorAll(".tg");for(var i=0;i<btns.length;i++){btns[i].addEventListener("click",function(){var v=this.getAttribute("data-set");document.documentElement.setAttribute("data-theme",v);try{localStorage.setItem("arbi_theme",v);}catch(e){}paint();});}paint();})();</script><div class="wrap">
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
  <p style="margin-top:8px"><a href="/log" style="color:var(--link);font-size:13px">📜 過去の判定を振り返る（あのとき◎→その後どう動いたか）</a></p>
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
  var __J=arbiJudge(snap); var score=__J.score, mark=__J.mark, label=__J.label, color=__J.color, reasons=__J.reasons, ok=__J.ok, __v=__J.volPct, rangePct=__J.rangePct, sd=__J.sd, __t1=__J.t1, __t2=__J.t2;
  jm.textContent=mark; jm.style.color=color; jl.textContent=label;  jl.style.color=color;
  try{
    var __key="arbi_judge_log";
    var __log=JSON.parse(localStorage.getItem(__key)||"[]");
    var __now=Date.now();
    var __sym=(snap&&snap.symbol)||"?";
    var __last=__log.length?__log[__log.length-1]:null;
    if(!(__last&&__last.symbol===__sym&&(__now-__last.ts)<60000)){
      __log.push({ts:__now,symbol:__sym,source:'binance-spot',via:'manual',price:(snap&&snap.price)||null,changePct:(snap&&snap.changePct)||null,mark:mark,label:label,trendDir:__J.trendDir,r1:null,r4:null,r24:null,conds:__J.conds,jv:'2.1'});
      if(__log.length>2000)__log=__log.slice(__log.length-2000);
      localStorage.setItem(__key,JSON.stringify(__log));
    }
  }catch(__e){}
  jr.innerHTML=(function(){var H="";if(!ok){var lh=document.createElement("li");lh.textContent="\u30c7\u30fc\u30bf\u4e0d\u8db3\u306e\u305f\u3081\u5224\u5b9a\u4fdd\u7559";H=lh.outerHTML;}else{var sg=(score>0?"+":"")+score;var ls=document.createElement("li");ls.textContent="\u30b9\u30b3\u30a2 "+sg+" \uff08"+mark+"\uff09";var dm={};(__J.conds||[]).forEach(function(c){dm[c.id]=c.dir;});function sy(d){return d>0?"\u25cb":(d<0?"\u2212":"\u30fb");}var bd="\u5185\u8a33: \u77ed\u671f\u30dc\u30e9 "+sy(dm.C1)+" / \u30c8\u30ec\u30f3\u30c9\u4e00\u81f4 "+sy(dm.C2)+" / 24h\u5024\u5e45 "+sy(dm.C3)+" / \u5b89\u5b9a\u5ea6 "+sy(dm.C4);var lb=document.createElement("li");lb.textContent=bd;H=ls.outerHTML+lb.outerHTML;}return H;})()+reasons.map(function(t){var li=document.createElement("li");li.textContent=t;return li.outerHTML;}).join("");
}
var goBtn=document.getElementById("go");
goBtn.onclick=async function(){
  var sym=document.getElementById("sym").value;
  var out=document.getElementById("out"); out.innerHTML="";
  try{ if(typeof WEIGHT_PROFILES!=="undefined"&&WEIGHT_PROFILES){ var __nv=document.createElement("div"); __nv.className="vpoint-note"; __nv.textContent="※「視点」はメンバー別の重み(v"+WEIGHT_PROFILES.version+")による参考値です。公式判定は全員共通のmarkです。"; out.appendChild(__nv); } }catch(__ne){}
  goBtn.disabled=true; goBtn.textContent="社員たちが分析中…";
  try{
    var tr=await fetch(API+"/api/v3/ticker/24hr?symbol="+sym).then(r=>r.json());
    var kl=await fetch(API+"/api/v3/klines?symbol="+sym+"&interval=1h&limit=24").then(r=>r.json());
    var closes=kl.map(function(k){return parseFloat(k[4]);});
    var snapshot={symbol:NAMES[sym],price:tr.lastPrice,changePct:tr.priceChangePercent,high24:tr.highPrice,low24:tr.lowPrice,hourlyCloses:closes,quoteVolume:(tr.quoteVolume||tr.volume||null),trades:(tr.count!=null?tr.count:null),wap:(tr.weightedAvgPrice||null),volPct:(function(){if(!closes||closes.length<3)return null;var r=[];for(var k=1;k<closes.length;k++){var a=parseFloat(closes[k-1]),b=parseFloat(closes[k]);if(a>0)r.push((b-a)/a*100);}if(!r.length)return null;var m=r.reduce(function(x,y){return x+y;},0)/r.length;var v=r.reduce(function(x,y){return x+(y-m)*(y-m);},0)/r.length;return Math.sqrt(v);})(),trendFirstHalf:(function(){if(!closes||closes.length<4)return null;var h=Math.floor(closes.length/2);var a=parseFloat(closes[0]),b=parseFloat(closes[h-1]);if(a>0)return (b-a)/a*100;return null;})(),trendSecondHalf:(function(){if(!closes||closes.length<4)return null;var h=Math.floor(closes.length/2);var a=parseFloat(closes[h]),b=parseFloat(closes[closes.length-1]);if(a>0)return (b-a)/a*100;return null;})()};
renderJudge(snapshot);
    var transcript=""; var step=0; var total=999;
    function mbBlock(step){try{
var keysL=["checker","spread","cost","transfer","liq","spread2","history","devil","audit"];
var NM={checker:"\u4e8b\u5b9f\u78ba\u8a8d\u4fc2\u30cf\u30b8\u30e1",spread:"\u4fa1\u683c\u5dee\u30a6\u30a9\u30c3\u30c1\u30e3\u30fc \u30b5\u30e4\u30df",cost:"\u30b3\u30b9\u30c8\u7cbe\u67fb\u5f79 \u30c6\u30b9\u30ea",transfer:"\u9001\u91d1\u30fb\u7d04\u5b9a\u30ea\u30b9\u30af\u4fc2 \u30aa\u30af\u30ea",liq:"\u6e05\u7b97\u30fb\u30ec\u30d0\u30ec\u30c3\u30b8\u4fc2 \u30bb\u30a4\u30b5\u30f3",spread2:"\u8cc7\u91d1\u5206\u6563\u4fc2 \u30d6\u30f3\u30b5\u30f3",history:"\u6b74\u53f2\u4fc2\u30b3\u30e8\u30df",devil:"\u60aa\u9b54\u306e\u4ee3\u5f01\u8005\u30a2\u30de\u30ce\u30b8\u30e3\u30af",audit:"\u76e3\u67fb\u5f79\u30ab\u30f3\u30b5"};
var key=keysL[step];if(!key)return "";
var WP=(typeof WEIGHT_PROFILES!=="undefined")?WEIGHT_PROFILES:null;
if(!WP||!WP.weights||!WP.weights[key])return "";
var w=WP.weights[key];
var lg;try{lg=JSON.parse(localStorage.getItem("arbi_judge_log")||"[]");}catch(e){return "";}
if(!lg||!lg.length)return "";
var hk="r1";var MOVE=0.3;
var cnt=0,dirN=0,dirHit=0,moveHit=0,absSum=0;
var c5cnt=0,c5cheap=0,c5neu=0,c5opp=0;
for(var i=0;i<lg.length;i++){
var r=lg[i];if(!r||!r.conds||!r.conds.length)continue;
var v=r[hk];if(v===null||v===undefined||isNaN(v))continue;
var ch=parseFloat(v);
var dir=r.trendDir||"neutral";var dirIsSet=(dir==="up"||dir==="down");
var hit=(dir==="up"&&ch>0)||(dir==="down"&&ch<0);
var moved=(Math.abs(ch)>=MOVE);
var s=0;for(var c=0;c<r.conds.length;c++){var cd=r.conds[c];if(cd&&w[cd.id]!=null)s+=cd.dir*w[cd.id];}
if(!(s>=2))continue;
cnt++;absSum+=Math.abs(ch);
if(dirIsSet){dirN++;if(hit)dirHit++;}
if(moved)moveHit++;
if(key==="spread"){for(var c2=0;c2<r.conds.length;c2++){var cc=r.conds[c2];if(cc&&cc.id==="C5"){c5cnt++;if(cc.dir>0)c5cheap++;else if(cc.dir===0)c5neu++;else c5opp++;}}}
}
var nm=NM[key]||key;
var H="\u3010\u3053\u306e\u8996\u70b9\uff08\u3042\u306a\u305f="+nm+"\uff09\u306e\u904e\u53bb\u306e\u632f\u308a\u8fd4\u308a\uff5c\u53c2\u8003\u30fb\u4ef6\u6570\u50c5\u5c11\u30fb\u512a\u52a3\u8a55\u4fa1\u3067\u306f\u3042\u308a\u307e\u305b\u3093\u3011";
var L=[H];
if(cnt===0){L.push("\u3053\u306e\u8996\u70b9\u3067\u307e\u3068\u307e\u3063\u305f\u5224\u5b9a\u304c\u7acb\u3063\u305f\u904e\u53bb\u30c7\u30fc\u30bf\u306f\u307e\u3060\u3042\u308a\u307e\u305b\u3093\u3002");}
else if(cnt<30){L.push("\u3042\u306a\u305f\u306e\u8996\u70b9\u3067\u5224\u5b9a\u304c\u7acb\u3063\u305f\u5834\u9762\uff1a"+cnt+"\u4ef6\u3002\u30b5\u30f3\u30d7\u30eb\u50c5\u5c11\u306e\u305f\u3081\u53c2\u8003\u7a0b\u5ea6\u3068\u3057\u3001\u5177\u4f53\u7684\u306a\u6570\u5024\u306f\u51fa\u3057\u307e\u305b\u3093\u3002");}
else{
var avg=Math.round((absSum/cnt)*100)/100;
var p2=Math.round((moveHit/cnt)*100);
var dirPart;
if(dirN<10){dirPart="\u65b9\u5411\u306e\u4e00\u81f4\uff1a\u6bcd\u6570\u304c\u5c11\u306a\u304f\u975e\u8868\u793a\uff08"+dirN+"\u4ef6\uff09";}
else{var p1=Math.round((dirHit/dirN)*100);dirPart="\u65b9\u5411\u306e\u4e00\u81f4\uff1a"+p1+"%\uff08\u6bcd\u6570"+dirN+"\u4ef6\uff09";}
L.push("\u3042\u306a\u305f\u306e\u8996\u70b9\u3067\u5224\u5b9a\u304c\u7acb\u3063\u305f\u5834\u9762\uff1a"+cnt+"\u4ef6\u3002"+dirPart+"\u30010.3%\u8d85\u306e\u53cd\u5fdc\uff1a"+p2+"%\u3001\u5e73\u5747\u5909\u52d5\uff1a"+avg+"%\u3002");
}
/* C5\u8a00\u53ca\u306f\u73fe\u72b6 spread(\u30b5\u30e4\u30df)\u306e\u307f\u3002\u5c06\u6765 C5\u91cd\u8996\u30e1\u30f3\u30d0\u30fc(\u4f8b: spread2)\u306b\u5e83\u3052\u308b\u5834\u5408\u306f\u3001\u4e0b\u8a18 key===\"spread\" \u3092\u5bfe\u8c61\u30ad\u30fc\u96c6\u5408\u306e\u5224\u5b9a\u306b\u5dee\u3057\u66ff\u3048\u308b(\u96c6\u8a08\u5074\u306e key===\"spread\" \u3068\u4e21\u65b9)\u3002\u4eca\u56de\u306f\u30b5\u30e4\u30df\u306e\u307f\u3067\u5909\u66f4\u306a\u3057\u3002 */
if(key==="spread"&&c5cnt>0){
if(c5cnt>=10){L.push("\u3046\u3061\u53d6\u5f15\u6240\u9593\u306e\u4e56\u96e2\uff08C5\uff09\u306b\u7740\u76ee\u3057\u305f\u5834\u9762\uff1a"+c5cnt+"\u4ef6\u3002\u4e56\u96e2\u306e\u5411\u304d\u306e\u5185\u8a33\uff1a\u5272\u5b89\u5074"+c5cheap+"\u4ef6\uff0f\u4e2d\u7acb"+c5neu+"\u4ef6\uff0f\u53cd\u5bfe\u5074"+c5opp+"\u4ef6\u3002");}
else{L.push("\u3046\u3061\u53d6\u5f15\u6240\u9593\u306e\u4e56\u96e2\uff08C5\uff09\u306b\u7740\u76ee\u3057\u305f\u5834\u9762\uff1a"+c5cnt+"\u4ef6\uff08\u5411\u304d\u306e\u5185\u8a33\u306f\u4ef6\u6570\u50c5\u5c11\u306e\u305f\u3081\u7701\u7565\uff09\u3002");}
}
L.push("\u203b\u3053\u308c\u306f\u904e\u53bb\u306e\u50be\u5411\u306e\u632f\u308a\u8fd4\u308a\u3067\u3042\u308a\u3001\u672a\u6765\u3092\u4fdd\u8a3c\u305b\u305a\u3001\u58f2\u8cb7\u30b5\u30a4\u30f3\u3067\u306f\u3042\u308a\u307e\u305b\u3093\u3002\u3053\u306e\u8996\u70b9\u304c\u52b9\u304d\u3084\u3059\u3044\uff0f\u52b9\u304d\u306b\u304f\u3044\u5c40\u9762\u306e\u7279\u6027\u7406\u89e3\u306b\u306e\u307f\u7528\u3044\u3001\u30e1\u30f3\u30d0\u30fc\u306e\u512a\u52a3\u5224\u65ad\u306b\u306f\u4f7f\u3044\u307e\u305b\u3093\u3002");
return L.join("\n")+"\n\n";
}catch(e){return "";}}
      var histStr=(function(){try{var lg=JSON.parse(localStorage.getItem('arbi_judge_log')||'[]');var sym=(snapshot&&snapshot.symbol)||'';var cur=(snapshot&&snapshot.price)||null;var rows=lg.filter(function(e){return e&&e.symbol===sym&&e.price&&e.mark&&e.ts;});if(!rows.length||!cur)return '';var byMark={};rows.forEach(function(e){var ch=((cur-e.price)/e.price)*100;if(!byMark[e.mark])byMark[e.mark]={n:0,up:0,sum:0};byMark[e.mark].n++;byMark[e.mark].sum+=ch;if(ch>0)byMark[e.mark].up++;});var lines=['\u3010\u904e\u53bb\u306e\u81ea\u5206\u305f\u3061\u306e\u5224\u5b9a\u5b9f\u7e3e\uff08\u540c\u3058\u901a\u8ca8\u30fb\u53c2\u8003\u60c5\u5831\uff09\u3011'];['\u25ce','\u25cb','\u25b3','\u00d7','?'].forEach(function(m){var d=byMark[m];if(!d)return;var avg=(d.sum/d.n).toFixed(2);var rate=Math.round((d.up/d.n)*100);lines.push('\u5224\u5b9a'+m+'\uff1a'+d.n+'\u4ef6\u3002\u305d\u306e\u5f8c\u3001\u73fe\u5728\u5024\u307e\u3067\u5e73\u5747'+avg+'%\uff08\u4e0a\u6607\u3057\u305f\u5272\u5408'+rate+'%\uff09');});if(lines.length<2)return '';lines.push('\u203b\u3053\u308c\u306f\u904e\u53bb\u306e\u50be\u5411\u306e\u53c2\u8003\u3067\u3042\u308a\u3001\u672a\u6765\u3092\u4fdd\u8a3c\u3059\u308b\u3082\u306e\u3067\u306f\u3042\u308a\u307e\u305b\u3093\u3002\u58f2\u8cb7\u30b5\u30a4\u30f3\u3067\u306f\u3042\u308a\u307e\u305b\u3093\u3002');return lines.join('\n');}catch(e){return '';}})();
      // ※順序はサーバーのMEETING_AGENDAと一致必須。メンバーの順序・人数を変更する際は両方を同時に更新すること
      var TEAM_KEYS=["checker","spread","cost","transfer","liq","spread2","history","devil","audit"];
      var __mj=null; try{ if(typeof arbiJudge==="function") __mj=arbiJudge(snapshot); }catch(__pe){ __mj=null; }
      while(step<total){
      var res=await fetch("/market_analyze",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({snapshot:snapshot,step:step,transcript:transcript,history:((typeof mbBlock==="function"?mbBlock(step):"")+histStr)})});
      var j=await res.json();
      if(j.error){ out.innerHTML+="<div class=\"speak err\">"+j.error+"</div>"; break; }
      total=j.total;
      var div=document.createElement("div"); div.className="speak";
      div.innerHTML="<div class=\"who\">"+j.who+"</div><div class=\"body\"></div>";
      try{
        var __wp=(typeof WEIGHT_PROFILES!=="undefined")?WEIGHT_PROFILES:null;
        var __mk=(TEAM_KEYS&&TEAM_KEYS[step])?TEAM_KEYS[step]:null;
        if(__wp&&__wp.weights&&__mk&&__wp.weights[__mk]&&__mj&&__mj.conds){
          var __w=__wp.weights[__mk];
          var __vm;
          if(__mj.ok===false){ __vm="?"; }
          else{
            var __s=0;
            __mj.conds.forEach(function(__c){ if(__w[__c.id]!=null){ __s+=__c.dir*__w[__c.id]; } });
            var __mark=(__s>=2)?"◎":((__s>=1)?"○":((__s>=0)?"△":"×"));
            var __sg=(__s>0?"+":"")+__s.toFixed(1);
            __vm=__mark+"（"+__sg+"）";
          }
          var __wd=div.querySelector(".who");
          if(__wd){ var __vs=document.createElement("span"); __vs.className="vpoint"; __vs.textContent=" 視点: "+__vm; __wd.appendChild(__vs); }
        }
      }catch(__ve){}
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
LOG_HTML = r"""<!doctype html><html lang="ja"><head><script>(function(){try{var t=localStorage.getItem("arbi_theme");if(t!=="A"&&t!=="B")t="A";document.documentElement.setAttribute("data-theme",t);}catch(e){document.documentElement.setAttribute("data-theme","A");}})();</script><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="/weights.js"></script>
<title>判定の振り返り — arbitrage</title>
<style>:root{--bg:#070d18;--tx:#eef3fa;--panel:#101d31;--panel2:#0b1626;--bd:#21385a;--bd2:#33506f;--mottobg:#101d31;--mut:#a3b6d0;--mut2:#8294ac;--mut3:#76889f;--head:#cdd9e6;--body2:#d6e0ee;--body3:#aebccd;--acc:#cdd9e6;--acctx:#0b1626;--up:#34d17f;--down:#ff5b5b;--flat:#aebccd;--link:#9fc0e6;}
[data-theme="A"]{--bg:#070d18;--tx:#eef3fa;--panel:#101d31;--panel2:#0b1626;--bd:#21385a;--bd2:#33506f;--mottobg:#101d31;--mut:#a3b6d0;--mut2:#8294ac;--mut3:#76889f;--head:#cdd9e6;--body2:#d6e0ee;--body3:#aebccd;--acc:#cdd9e6;--acctx:#0b1626;--up:#34d17f;--down:#ff5b5b;--flat:#aebccd;--link:#9fc0e6;}
[data-theme="B"]{--bg:#fdfaf6;--tx:#33302c;--panel:#ffffff;--panel2:#fffdfa;--bd:#efe7dd;--bd2:#e6dbcf;--mottobg:#ffffff;--mut:#6f665d;--mut2:#857b71;--mut3:#94897e;--head:#4a443d;--body2:#48423b;--body3:#5a534b;--acc:#bc8378;--acctx:#ffffff;--up:#3f9b72;--down:#c8635c;--flat:#8c837b;--link:#b06b5f;}
[data-theme="B"] .motto,[data-theme="B"] .coin,[data-theme="B"] .panel,[data-theme="B"] .judge,[data-theme="B"] .speak,[data-theme="B"] .card{border-radius:24px;box-shadow:0 10px 28px -16px rgba(170,120,110,.40);border-color:#f3ece4;}
[data-theme="B"] button.go,[data-theme="B"] .btn{border-radius:24px;box-shadow:0 12px 26px -10px rgba(188,131,120,.55);}
[data-theme="B"] .coin{transition:transform .25s,box-shadow .25s;}
[data-theme="B"] .coin:hover{transform:translateY(-4px);box-shadow:0 16px 32px -14px rgba(170,120,110,.50);}
[data-theme="B"] .note{border-radius:18px;}

body{font-family:system-ui,-apple-system,"Segoe UI",sans-serif;max-width:880px;margin:0 auto;padding:24px;background:var(--bg);color:var(--tx);line-height:1.7}
a{color:var(--link)}h1{font-size:22px}.muted{color:var(--mut);font-size:14px}
.card{background:var(--panel);border:1px solid var(--bd);border-radius:12px;padding:16px;margin:14px 0}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:8px 6px;border-bottom:1px solid var(--bd)}
.mark{font-size:18px;font-weight:bold}.up{color:var(--up)}.down{color:var(--down)}.flat{color:var(--flat)}
.note{background:var(--panel2);border:1px dashed var(--bd2);border-radius:10px;padding:12px;color:var(--mut);font-size:13px;margin:12px 0}
.btn{display:inline-block;background:var(--acc);color:var(--acctx);padding:8px 14px;border-radius:8px;text-decoration:none;border:none;cursor:pointer;font-size:14px}
</style></head><body><div class="themebar" style="display:flex;gap:6px;justify-content:flex-end;margin:0 0 6px;"><button type="button" class="tg" data-set="A" style="font:inherit;cursor:pointer;border:1px solid var(--bd2);background:var(--panel);color:var(--tx);border-radius:999px;padding:5px 12px;font-size:12px;">🌙 紺</button><button type="button" class="tg" data-set="B" style="font:inherit;cursor:pointer;border:1px solid var(--bd2);background:var(--panel);color:var(--tx);border-radius:999px;padding:5px 12px;font-size:12px;">☀ 白</button></div><script>(function(){function cur(){return document.documentElement.getAttribute("data-theme")||"A";}function paint(){var c=cur();var b=document.querySelectorAll(".tg");for(var i=0;i<b.length;i++){var on=b[i].getAttribute("data-set")===c;b[i].style.fontWeight=on?"700":"400";b[i].style.opacity=on?"1":".55";}}var btns=document.querySelectorAll(".tg");for(var i=0;i<btns.length;i++){btns[i].addEventListener("click",function(){var v=this.getAttribute("data-set");document.documentElement.setAttribute("data-theme",v);try{localStorage.setItem("arbi_theme",v);}catch(e){}paint();});}paint();})();</script>
<p><a href="/market">&larr; 市場室へ</a> &nbsp; <a href="/">arbitrage トップ</a></p>
<h1>📜 判定の振り返り（社員たちが向上するための記録）</h1>
<p class="muted">市場室で出した自動判定（◎○△×?）を、この端末に記録しています。後から「あのとき◎と言ったが、その後どう動いたか」を今の価格と見比べて、次に活かすためのページです。これは教育用で、売買のおすすめではありません。</p>
<div class="note">※ 記録はこの端末（ブラウザ）の中だけに保存され、外部には送信されません。市場室で判定するほど記録が増えます。</div>
<div class="card"><div id="summary" class="muted">読み込み中…</div></div><div class="card"><div id="summary2" class="muted">答え合わせ集計を計算中…</div></div><div class="card"><div id="board"></div></div><div class="card"><div id="cboard"></div></div>
<div class="card"><div id="mboard"></div></div>
<div class="card"><table><thead><tr><th>日時</th><th>通貨</th><th>判定</th><th>当時の価格</th><th>今の価格</th><th>その後</th></tr></thead><tbody id="rows"><tr><td colspan="6" class="muted">記録がまだありません。市場室で判定してみてください。</td></tr></tbody></table></div>
<p><button class="btn" id="exportBtn">バックアップを保存</button> <button class="btn" id="importBtn">バックアップから復元</button> <button class="btn" id="serverImportBtn">サーバー記録を取り込む</button><input type="file" id="importFile" accept="application/json,.json" style="display:none"></p>
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
function applyV1Records(obj){
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
    }
    var __sib=document.getElementById("serverImportBtn");
    if(__sib){
      __sib.onclick=function(){
        fetch("/api/export-v1").then(function(r){return r.json();}).then(function(obj){
          if(obj && obj.error){ alert("サーバーエラー: "+obj.error); return; }
          applyV1Records(obj);
        }).catch(function(e){ alert("サーバー記録の取り込みに失敗しました（通信エラー）"); });
      };
    }
    var __ib=document.getElementById("importBtn");var __if=document.getElementById("importFile");
if(__ib&&__if){
  __ib.onclick=function(){__if.value="";__if.click();};
  __if.onchange=function(){
    var file=__if.files&&__if.files[0];if(!file)return;
    var reader=new FileReader();
    reader.onload=function(){
      var obj;try{obj=JSON.parse(reader.result);}catch(e){alert("読み込み失敗：JSONを解析できませんでした。");return;}
      applyV1Records(obj);
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
var __cHorizon="r1";var CB_HKEYS=[["r1","1\u6642\u9593\u5f8c"],["r4","4\u6642\u9593\u5f8c"],["r24","24\u6642\u9593\u5f8c"]];var CB_IDS=["C1","C2","C3","C4"];var CB_NAMES={C1:"C1 \u77ed\u671f\u30dc\u30e9",C2:"C2 \u524d\u5f8c\u534a\u30c8\u30ec\u30f3\u30c9\u4e00\u81f4",C3:"C3 24h\u5024\u5e45",C4:"C4 \u6642\u9593\u8db3sd"};function cbDirLabel(d){return d>0?"+1":(d<0?"-1":"0");}function drawCBoard(){var el=document.getElementById("cboard");if(!el)return;var log=boardRead();var hk=__cHorizon;var gFire=0;var anyData=false;var buckets={};for(var i=0;i<log.length;i++){var r=log[i];if(!r||!r.conds||!r.conds.length)continue;var hasG=false;for(var g=0;g<r.conds.length;g++){if(r.conds[g]&&r.conds[g].id==="G")hasG=true;}if(hasG){gFire++;continue;}var v=r[hk];if(v===null||v===undefined||isNaN(v))continue;var ch=parseFloat(v);anyData=true;for(var c=0;c<r.conds.length;c++){var cd=r.conds[c];if(!cd||CB_IDS.indexOf(cd.id)<0)continue;var key=cd.id+"|"+cd.dir;if(!buckets[key])buckets[key]={id:cd.id,dir:cd.dir,cnt:0,dirN:0,dirHit:0,moveHit:0,absSum:0};var bk=buckets[key];bk.cnt++;bk.absSum+=Math.abs(ch);if(cd.dir!==0){if(Math.abs(ch)>=BOARD_MOVE_THRESH)bk.moveHit++;var dir=r.trendDir||"neutral";if(dir==="up"||dir==="down"){bk.dirN++;if((dir==="up"&&ch>0)||(dir==="down"&&ch<0))bk.dirHit++;}}}}var btns="";for(var b=0;b<CB_HKEYS.length;b++){var hkk=CB_HKEYS[b][0];var hlbl=CB_HKEYS[b][1];btns+='<button class="btn'+(hkk===hk?" on":"")+'" data-chz="'+hkk+'" style="margin-right:6px">'+hlbl+'</button>';}var head='<h3 style="margin:0 0 8px">\u6761\u4ef6\u5225\u306e\u6210\u7e3e</h3><div style="margin-bottom:8px">'+btns+'</div>';if(!anyData){el.innerHTML=head+'<div class="muted">\u307e\u3060\u6761\u4ef6\u5225\u30c7\u30fc\u30bf\u304c\u3042\u308a\u307e\u305b\u3093\u3002\u2463-A\u4ee5\u964d\u306e\u5224\u5b9a\u304c\u7b54\u3048\u5408\u308f\u305b\u3055\u308c\u308b\u3068\u3053\u3053\u306b\u8868\u793a\u3055\u308c\u307e\u3059</div>'+'<div class="muted" style="margin-top:6px">G\u30b2\u30fc\u30c8\u767a\u706b: '+gFire+'\u56de</div>';cboardBind();return;}var rowsHtml="";var order=[1,-1,0];for(var k=0;k<CB_IDS.length;k++){var id=CB_IDS[k];for(var o=0;o<order.length;o++){var dv=order[o];var bk=buckets[id+"|"+dv];if(!bk)continue;var p1=(dv!==0)?boardPct(bk.dirHit,bk.dirN):null;var p2=(dv!==0)?boardPct(bk.moveHit,bk.cnt):null;var avg=bk.cnt?(Math.round(bk.absSum/bk.cnt*100)/100):null;var few=(bk.cnt>0&&bk.cnt<30)?' <span class="muted">\u4ef6\u6570\u50fc\u5c11\uff08\u53c2\u8003\u5024\uff09</span>':"";var c1=(dv===0)?"\u2014":(p1===null?"\u2014":p1+"%");var c2=(dv===0)?"\u2014":(p2===null?"\u2014":p2+"%");var c3=(avg===null?"\u2014":avg+"%");rowsHtml+="<tr><td>"+CB_NAMES[id]+"</td><td>"+cbDirLabel(dv)+"</td><td>"+bk.cnt+few+"</td><td>"+c1+"</td><td>"+c2+"</td><td>"+c3+"</td></tr>";}}var tbl='<table><thead><tr><th>\u6761\u4ef6</th><th>\u767a\u706b</th><th>\u4ef6\u6570</th><th>\u65b9\u5411\u7684\u4e2d\u7387</th><th>\u00b10.3%\u4ee5\u4e0a</th><th>\u5e73\u5747\u5909\u5316\u5e45</th></tr></thead><tbody>'+rowsHtml+'</tbody></table>';var gline='<div class="muted" style="margin-top:6px">G\u30b2\u30fc\u30c8\u767a\u706b: '+gFire+'\u56de\uff08\u6210\u7e3e\u8a08\u7b97\u5bfe\u8c61\u5916\uff09</div>';el.innerHTML=head+tbl+gline;cboardBind();}function cboardBind(){var el=document.getElementById("cboard");if(!el)return;var bs=el.querySelectorAll("button[data-chz]");for(var i=0;i<bs.length;i++){bs[i].onclick=function(){__cHorizon=this.getAttribute("data-chz");drawCBoard();};}}
var __mHorizon="r1";
var MB_KEYS=["checker","spread","cost","transfer","liq","spread2","history","devil","audit"];
var MB_NAMES={checker:"\u4e8b\u5b9f\u78ba\u8a8d\u4fc2\u30cf\u30b8\u30e1",spread:"\u4fa1\u683c\u5dee\u30a6\u30a9\u30c3\u30c1\u30e3\u30fc\u0020\u30b5\u30e4\u30df\u2696\ufe0f",cost:"\u30b3\u30b9\u30c8\u7cbe\u67fb\u5f79\u0020\u30c6\u30b9\u30ea\ud83e\uddee",transfer:"\u9001\u91d1\u30fb\u7d04\u5b9a\u30ea\u30b9\u30af\u4fc2\u0020\u30aa\u30af\u30ea\ud83d\ude9a",liq:"\u6e05\u7b97\u30fb\u30ec\u30d0\u30ec\u30c3\u30b8\u4fc2\u0020\u30bb\u30a4\u30b5\u30f3\u26a0\ufe0f",spread2:"\u8cc7\u91d1\u5206\u6563\u4fc2\u0020\u30d6\u30f3\u30b5\u30f3\ud83d\udce6",history:"\u6b74\u53f2\u4fc2\u30b3\u30e8\u30df\ud83d\udcdc",devil:"\u60aa\u9b54\u306e\u4ee3\u5f01\u8005\u30a2\u30de\u30ce\u30b8\u30e3\u30af\ud83d\ude08",audit:"\u76e3\u67fb\u5f79\u30ab\u30f3\u30b5\ud83d\udd0d"};
function mbMark(s){return (s>=2)?"\u25ce":((s>=1)?"\u25cb":((s>=0)?"\u25b3":"\u00d7"));}
function drawMBoard(){
  var el=document.getElementById("mboard");if(!el)return;
  if(typeof WEIGHT_PROFILES==="undefined"||!WEIGHT_PROFILES||!WEIGHT_PROFILES.weights){el.innerHTML="";return;}
  var WP=WEIGHT_PROFILES;var log=boardRead();var hk=__mHorizon;
  var stats={};for(var ki=0;ki<MB_KEYS.length;ki++){stats[MB_KEYS[ki]]={cnt:0,dirN:0,dirHit:0,moveHit:0,absSum:0};}
  var anyData=false;
  for(var i=0;i<log.length;i++){
    var r=log[i];if(!r||!r.conds||!r.conds.length)continue;
    var v=r[hk];if(v===null||v===undefined||isNaN(v))continue;
    var ch=parseFloat(v);anyData=true;
    var dir=r.trendDir||"neutral";var dirIsSet=(dir==="up"||dir==="down");
    var hit=(dir==="up"&&ch>0)||(dir==="down"&&ch<0);
    var moved=(Math.abs(ch)>=BOARD_MOVE_THRESH);
    for(var ki2=0;ki2<MB_KEYS.length;ki2++){
      var key=MB_KEYS[ki2];var w=WP.weights[key];if(!w)continue;
      var s=0;for(var c=0;c<r.conds.length;c++){var cd=r.conds[c];if(cd&&w[cd.id]!=null)s+=cd.dir*w[cd.id];}
      if(mbMark(s)!=="\u25ce")continue;
      var st=stats[key];st.cnt++;st.absSum+=Math.abs(ch);
      if(dirIsSet){st.dirN++;if(hit)st.dirHit++;}
      if(moved)st.moveHit++;
    }
  }
  var btns="";for(var b=0;b<BOARD_HKEYS.length;b++){var hkk=BOARD_HKEYS[b][0];var hlbl=BOARD_HKEYS[b][1];btns+='<button class="btn"'+(hkk===hk?" on":"")+' data-mhz="'+hkk+'" style="margin-right:6px">'+hlbl+"</button>";}
  var head='<div style="margin-bottom:8px">'+btns+"</div>";
  var titleLine='<div style="font-weight:600;margin-bottom:4px">\u30e1\u30f3\u30d0\u30fc\u5225\u0020\u6210\u7e3e\u0028\u8996\u70b9\u30ea\u30fc\u30b0\u6226\u0029</div>';
  var explLine='<div class="muted" style="margin-bottom:6px">\u25ce\u306f\u0022\u6761\u4ef6\u304c\u5b89\u5b9a\u0022\u306e\u898b\u7acb\u3066\u3002\u00b1\u0030\u002e\u0033\u0025\u7387\u304c\u4f4e\u3044\u307b\u3069\u898b\u7acb\u3066\u901a\u308a\u3060\u3063\u305f\u3053\u3068\u3092\u793a\u3057\u307e\u3059</div>';
  if(!anyData){el.innerHTML=titleLine+head+'<div class="muted">\u7b54\u3048\u5408\u308f\u305b\u6e08\u307f\u306e\u0063\u006f\u006e\u0064\u0073\u4ed8\u304d\u30c7\u30fc\u30bf\u304c\u84c4\u7a4d\u3055\u308c\u308b\u3068\u3001\u30e1\u30f3\u30d0\u30fc\u5225\u306e\u9806\u4f4d\u304c\u8868\u793a\u3055\u308c\u307e\u3059\u3002</div>';mboardBind();return;}
  var rows=[];for(var ki3=0;ki3<MB_KEYS.length;ki3++){var k2=MB_KEYS[ki3];var st2=stats[k2];
    var p1=st2.dirN?boardPct(st2.dirHit,st2.dirN):null;
    var p2=st2.cnt?boardPct(st2.moveHit,st2.cnt):null;
    var avg=st2.cnt?(Math.round(st2.absSum/st2.cnt*100)/100):null;
    rows.push({key:k2,cnt:st2.cnt,p1:p1,p2:p2,avg:avg});}
  rows.sort(function(a,b){var pa=(a.p2===null)?Infinity:a.p2;var pb=(b.p2===null)?Infinity:b.p2;if(pa!==pb)return pa-pb;return b.cnt-a.cnt;});
  var rowsHtml="";for(var ri=0;ri<rows.length;ri++){var rw=rows[ri];
    var few=(rw.cnt>0&&rw.cnt<30)?' <span class="muted">\u4ef6\u6570\u50c5\u5c11\uff08\u53c2\u8003\u5024\uff09</span>':"";
    var c1=(rw.p1===null)?"\u2014":(rw.p1+"%");
    var c2=(rw.p2===null)?"\u2014":(rw.p2+"%");
    var c3=(rw.avg===null)?"\u2014":(rw.avg+"%");
    rowsHtml+="<tr><td>"+(ri+1)+"</td><td>"+MB_NAMES[rw.key]+"</td><td>"+rw.cnt+few+"</td><td>"+c1+"</td><td>"+c2+"</td><td>"+c3+"</td></tr>";}
  var tbl='<table><thead><tr><th>\u9806\u4f4d</th><th>\u30e1\u30f3\u30d0\u30fc</th><th>\u25ce\u4ef6\u6570</th><th>\u65b9\u5411\u7684\u4e2d\u7387</th><th>\u00b1\u0030\u002e\u0033\u0025\u4ee5\u4e0a\u7387</th><th>\u5e73\u5747\u5909\u5316\u5e45</th></tr></thead><tbody>'+rowsHtml+"</tbody></table>";
  var ver=(WP.version!=null?WP.version:"?");
  var note='<div class="muted" style="margin-top:6px">\u91cd\u307f\u0076"+ver+"\u306b\u3088\u308b\u9061\u53ca\u8a08\u7b97</div>';
  el.innerHTML=titleLine+explLine+head+tbl+note;mboardBind();
}
function mboardBind(){var el=document.getElementById("mboard");if(!el)return;var bs=el.querySelectorAll("button[data-mhz]");for(var i=0;i<bs.length;i++){bs[i].onclick=function(){__mHorizon=this.getAttribute("data-mhz");drawMBoard();};}}
drawCBoard();
drawMBoard();
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
        MEMORY_GUARD,
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

@app.route("/judge.js")
def judge_js():
    with open("judge.js", "r", encoding="utf-8") as f:
        js = f.read()
    resp = Response(js, mimetype="application/javascript")
    resp.headers["Cache-Control"] = "no-cache"
    return resp

@app.route("/weights.js")
def weights_js():
    with open("weights.js", "r", encoding="utf-8") as f:
        js = f.read()
    resp = Response(js, mimetype="application/javascript")
    resp.headers["Cache-Control"] = "no-cache"
    return resp

@app.route("/api/export-v1")
def api_export_v1():
    db_url = os.environ.get("NEON_DATABASE_URL")
    if not db_url:
        return jsonify({"format": "v1", "error": "NEON_DATABASE_URL not configured", "count": 0, "data": []})
    conn = None
    try:
        import psycopg2
        conn = psycopg2.connect(db_url, sslmode="require")
        cur = conn.cursor()
        cur.execute(
            "SELECT ts, symbol, source, via, price, change_pct, mark, label, trend_dir, r1, r4, r24, conds, judge_ver "
            "FROM (SELECT * FROM judge_records ORDER BY ts DESC LIMIT 2000) sub ORDER BY ts ASC"
        )
        rows = cur.fetchall()
        data = []
        for r in rows:
            ts_val = r[0]
            ts_ms = int(ts_val.timestamp() * 1000) if ts_val is not None else None
            data.append({
                "ts": ts_ms,
                "symbol": r[1],
                "source": r[2],
                "via": r[3],
                "price": r[4],
                "changePct": r[5],
                "mark": r[6],
                "label": r[7],
                "trendDir": r[8],
                "r1": r[9],
                "r4": r[10],
                "r24": r[11],
                "conds": r[12] if r[12] is not None else [],
                "jv": r[13],
            })
        cur.close()
        resp = jsonify({"format": "v1", "exportedAt": __import__("datetime").datetime.utcnow().isoformat() + "Z", "count": len(data), "data": data})
        resp.headers["Cache-Control"] = "no-cache"
        return resp
    except Exception as e:
        return jsonify({"format": "v1", "error": str(e), "count": 0, "data": []})
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

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
