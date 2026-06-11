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
RULES = """あなたは「kabuka」のAIアナリストです。経済・投資・お金についての質問に答えます。
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
    {"key": "fact", "emoji": "\U0001F50E", "name": "事実確認＆情報の番人 ウラトリ", "job": "あなたは事実確認と情報の鮮度の番人です。短期売買では噂・SNSの急騰話・出どころ不明のシグナルに飛びつく事故が多い、という前提で答えます。実演として、板の厚さ・出来高・スプレッド・直近の値動きを、どの数字をどの順で確認するかを示してください。SNSやシグナル業者の主張が出たら、一次情報（取引所の実データ）でどう裏を取るかを具体的に言うこと。安全として、出どころ不明・古い・一情報源だけの3点は必ず警告し、あなたはリアルタイムの最新値を持たないと正直に言い、最終確認は本人に促してください。4～6文で。"},
    {"key": "numbers", "emoji": "\U0001F9EE", "name": "数字の人 カズオ", "job": "あなたは計算・クオンツ・サヤ取りの3役を兼ねます。実演として、短期トレード1回の損益を『入る根拠／損切り幅／利確幅／回数』に分け、手数料・スプレッド・スリッピージ・税を引いた“手取り”で考えて見せてください。リスクリワード比（損小利大）や、回数が増えるほどコストが積み上がる様子にも触れること。サヤ取りが関係するなら、理論上のサヤがコストでどう削れるかも示す。安全として、過去の値動きは未来を保証しない・関係が壊れれば一気に大損する・『リスクなしのもうけ』は幻想で天才ファンドさえ破綻した、を必ず添える。専門用語はかみくだくこと。5～7文で。"},
    {"key": "history", "emoji": "\U0001F4DC", "name": "歴史と前提の人 コヨミ", "job": "あなたは歴史と前提の担当です。実演として、過去の暗号資産の具体的な事故（取引所破綻、レバレッジ清算の連鎖、急騰直後の急落、流動性が一瞬で消える場面）を1～2例挙げ、そのとき短期トレーダーが何で間違えたかを振り返ってください。安全として、歴史は同じには繰り返さないと添え、年代・国・税制・前提が違えば結論も変わること、最終判断は本人に委ねる姿勢を示すこと。4～6文で。"},
    {"key": "devil", "emoji": "\U0001F608", "name": "悪魔の代弁者 アマノジャク", "job": "あなたは悪魔の代弁者でありブレーキ役です。実演として、いま出ている見方に対し、『逆に動いたら』『約定できなかったら』『出金が止まったら』『レバレッジで清算されたら』という具体シナリオを突きつけ、各手法の最悪ケースを示してください。安全として、『絶対上がる』『これは鉄板』という空気を強く疑い、断定が出ていたら止めること。楽観のまちがいに誰より早く気づかせる。3～5文で。"},
    {"key": "beginner", "emoji": "\U0001F423", "name": "伝える人 ハジメ", "job": "あなたは素人代表です。ここまでの会議を、短期トレード（スキャル・デイトレ・サヤ取り）を初めて触る人にもわかるよう、やさしい言葉と身近なたとえで“流れ”として見せてください（何を見て入り、どこで逃げるか、を物語にする）。難しい用語は『つまり、こういうこと』と言いかえること。派手な利益より『退場しない・大損しない』が目標だと、やさしく言い添える。3～5文で。"},
    {"key": "audit", "emoji": "\U0001F50D", "name": "監査役 カンサ", "job": "あなたはミス発見が最上級のプロです。全員の発言を総点検し、短期トレード特有の甘い見積もり（手数料・税・約定ズレの軽視、勝率の過大評価、損切りずらし）に遠慮なく赤ペンを入れてください（ただし自分は『絶対』『確実に儲かる』と断定しないこと）。利用者が次に自分で確認すべきことを1つ示し、最後に、これは教育・情報提供であって個別の売買の指示ではないこと、最終判断は本人の責任であることを、おだやかに念押しして会議を締めること。4～6文で。"},
]

def build_meeting_system(role, lang):
    lang_name = LANG_NAMES.get(lang, "日本語")
    parts = [
        RULES,
        "",
        "あなたは投資情報会社kabukaの社員「" + role["name"] + "」として、社員会議で発言します。",
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
        "必ず「" + lang_name + "」で書いてください。",
    ]
    return "\n".join(parts)

HOME_HTML = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>kabuka — 取引所間 先物サヤ取りの投資情報会社</title>
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
  <div class="topbar"><span class="brand">kabuka</span><span class="badge">投資・お金の情報・教育</span></div>
  <h1 class="hero">ようこそ kabuka へ</h1>
  <p class="lead">世界中の人が、初心者からプロまで、自分の言語で使える「投資・お金の情報会社」。ここは情報・教育の場です。</p>
  <div style="background:#e3f1ec;border:1px solid #cfe5dd;border-radius:14px;padding:14px 16px;margin:0 0 18px"><p style="font-size:15px;font-weight:700;color:#0f7a5f;margin:0 0 6px">🧭 わたしたちのモットー：「まちがいに早く気づく会社」</p><p style="font-size:12.5px;color:#5d6470;margin:0">絶対に勝つことはできません。だからこそ、すぐに結論を出さない・まちがえても責めない・わからないときは「わからない」と言える——そんな環境を大切にします。</p></div>
<div class="flow"><span>世界の情報</span><span class="arw">→</span><span>kabukaの中で読み解く</span><span class="arw">→</span><span>あなた（世界の利用者）へ</span></div>
  <div class="building">
    <div class="building-title">kabuka — あなたの投資情報会社</div>
    <div class="rooms">
      <a class="room analyze full" href="/analyst">
        <p class="rt">💬 受付カウンター（AIアナリスト）</p>
        <p class="rd">情報をチェックし、冷静に分析し、あなたの言語とレベルで答えます。質問してみてください。</p>
      </a>
      <a class="room jade" href="/market">
        <p class="rt">📈 株価グラフ＆分析</p>
        <p class="rd">本物のリアルタイム価格をグラフで見て、社員の分析メモ付きで読む。</p>
      </a>
      <a class="room safe" href="/renshujo">
        <p class="rt">🎯 投資の練習場</p>
        <p class="rd">積立・分散・ファクターなどを、リスクなしで試して学ぶ。</p>
      </a>
      <a class="room safe full" href="/shain">
<p class="rt">👥 社員紹介室</p>
<p class="rd">kabukaで働く社員たちと、それぞれが守る約束を見る。</p>
</a>
<a class="room jade full" href="/kaigi">
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
<a class="room safe full" href="/kihon">
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
  <div class="foot">kabuka は教育・情報提供を目的としたサービスです。お金を運用するものではなく、利益を保証するものでもありません。投資にはリスクがあり、最終的な判断はご自身の責任で行ってください。</div>
</div>
</body>
</html>"""

ANALYST_HTML = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>kabuka — AIアナリスト</title>
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
  <p style="margin:0 0 14px"><a href="/" style="font-size:13px;color:#0f7a5f;text-decoration:none">← kabuka トップへ</a></p>
  <div class="topbar">
    <span class="brand">kabuka</span>
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
    kabuka のAIアナリストは、プロが使う分析の作法で中立に読み解くAIです。AIによる情報提供であり、利益を保証するものではありません。投資の判断はご自身の責任で行ってください。
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
<title>kabuka — 投資の練習場</title>
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
  <a class="back" href="/">← kabuka トップへ</a>
  <p class="brand">kabuka</p>
  <h1 class="hero">投資の練習場</h1>
  <p class="lead">すべて架空のお金です。本物のお金は使いません。安全に、投資のやり方を体験しましょう。</p>
  <div class="grid">
    <a class="card" href="/kihon">
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
<title>kabuka — 練習投資シミュレーター</title>
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
  <p style="margin:0 0 14px"><a href="/renshujo" style="font-size:13px;color:#0f7a5f;text-decoration:none">← 練習場へ</a></p>

  <div class="topbar">
    <span class="brand">kabuka</span>
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
<title>kabuka — ファクター投資の練習</title>
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
  <p style="margin:0 0 14px"><a href="/renshujo" style="font-size:13px;color:#0f7a5f;text-decoration:none">← 練習場へ</a></p>

  <div class="topbar">
    <span class="brand">kabuka</span>
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
<title>kabuka — アービトラージの練習</title>
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
  <p style="margin:0 0 14px"><a href="/renshujo" style="font-size:13px;color:#0f7a5f;text-decoration:none">← 練習場へ</a></p>

  <div class="topbar">
    <span class="brand">kabuka</span>
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
<title>kabuka — 社員紹介室</title>
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
<p style="margin:0 0 14px"><a href="/" style="font-size:13px;color:#0f7a5f;text-decoration:none">← kabuka トップへ</a></p>
<div class="topbar"><span class="brand">kabuka</span><span class="badge">社員紹介室</span></div>
<h1 class="hero">うちの社員たち</h1>
<p class="lead">「負けない会社」をつくるために集めた仲間です。一人ひとりが、破ってはいけない約束のどれかを担当しています。スター選手はいません。でも、みんなで支え合います。</p>
<a href="/kaigi" style="display:inline-block;text-decoration:none;background:#0f7a5f;color:#fff;font-weight:500;font-size:14px;padding:11px 18px;border-radius:10px;margin:0 0 18px">🗣️ この人たちで会議してもらう →</a>
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
<div class="foot">kabuka は教育・情報提供を目的としたサービスです。利益を保証するものではなく、投資の判断はご自身の責任で行ってください。</div>
</div>
</body>
</html>
"""

KAIGI_HTML = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>kabuka — 社員会議室</title>
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
<p style="margin:0 0 14px"><a href="/" style="font-size:13px;color:#0f7a5f;text-decoration:none">← kabuka トップへ</a></p>
<div class="topbar"><span class="brand">kabuka</span><span class="badge">社員会議室</span></div>
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
async function run(){var q=input.value.trim();if(!q)return;btn.disabled=true;btn.textContent="会議中…";box.innerHTML="";var transcript="";for(var step=0;;step++){var t=bubble("💭","社員が考えています…","",true);var data;try{var r=await fetch("/meeting",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({question:q,step:step,transcript:transcript,lang:lang})});data=await r.json();}catch(err){t.classList.remove("think");t.querySelector(".btext").textContent="通信でエラーが起きました。少し待ってもう一度ためしてください。";break;}if(data.error){t.classList.remove("think");t.querySelector(".btext").textContent="うまくいきませんでした："+data.error;break;}TOTAL=data.total;t.classList.remove("think");t.querySelector(".bemo").textContent=data.emoji;t.querySelector(".bname").textContent=data.speaker;t.querySelector(".btext").textContent=data.text;transcript+=data.speaker+"："+data.text+"\n\n";window.scrollTo(0,document.body.scrollHeight);if(step>=TOTAL-1)break;}var end=document.createElement("div");end.className="endnote";end.textContent="会議は以上です。これは教育・情報提供で、個別の売買アドバイスではありません。最終的な判断はご自身の責任で行ってください。";box.appendChild(end);btn.disabled=false;btn.textContent="もう一度 会議する";}
btn.addEventListener("click",run);
</script>
</body>
</html>
"""

@app.route("/")
def home():
    return Response(HOME_HTML, mimetype="text/html")

@app.route("/analyst")
def analyst():
    return Response(ANALYST_HTML, mimetype="text/html")

@app.route("/renshujo")
def renshujo():
    return Response(RENSHUJO_HTML, mimetype="text/html")

@app.route("/kihon")
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
<title>取引所間 先物サヤ取り市場室 — kabuka</title>
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
</style></head><body><div class="wrap">
<h1>📈 取引所間 先物サヤ取り市場室</h1>
<p class="sub">複数取引所のリアルタイム価格を見て、社員たちが取引所間の先物価格差（アービトラージ）の観点から判断・分析する部屋です。</p>
<div class="motto">🧭 モットー：まちがいに早く気づく会社。ここは投資情報会社kabukaの<strong>『取引所間 先物サヤ取り市場室』</strong>です。同じ先物の取引所間の価格差を、手数料・送金・税を引いた“手取り”の目線で判断・分析します。社員は「絶対もうかる」とは言わず、わからないことは正直に言います。投資の判断は、いつもあなた自身のものです。</div>
<div id="grid" class="grid"><div class="coin">読み込み中…</div></div>
<p id="upd" class="upd"></p>
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
loadGrid(); setInterval(loadGrid, 10000);
var goBtn=document.getElementById("go");
goBtn.onclick=async function(){
  var sym=document.getElementById("sym").value;
  var out=document.getElementById("out"); out.innerHTML="";
  goBtn.disabled=true; goBtn.textContent="社員たちが分析中…";
  try{
    var tr=await fetch(API+"/api/v3/ticker/24hr?symbol="+sym).then(r=>r.json());
    var kl=await fetch(API+"/api/v3/klines?symbol="+sym+"&interval=1h&limit=24").then(r=>r.json());
    var closes=kl.map(function(k){return parseFloat(k[4]);});
    var snapshot={symbol:NAMES[sym],price:tr.lastPrice,changePct:tr.priceChangePercent,high24:tr.highPrice,low24:tr.lowPrice,hourlyCloses:closes};
    var transcript=""; var step=0; var total=999;
    while(step<total){
      var res=await fetch("/market_analyze",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({snapshot:snapshot,step:step,transcript:transcript})});
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
        "ここは投資情報会社kabukaの『取引所間 先物サヤ取り市場室』です。複数取引所のリアルタイム価格データを見て、取引所間の先物価格差（アービトラージ）の観点から判断・分析する場です。",
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
        "発言は" + lang_name + "で、4〜5文の短さで。自分の役割に集中し、前の人と同じことはくり返さない。",
    ]
    return "\n".join(parts)

@app.route("/market")
def market():
    return Response(MARKET_HTML, mimetype="text/html")

@app.route("/market_analyze", methods=["POST"])
def market_analyze():
    data = request.get_json(force=True, silent=True) or {}
    snap = data.get("snapshot") or {}
    step = int(data.get("step", 0))
    transcript = (data.get("transcript") or "").strip()
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
        + "直近24時間の1時間ごとの終値：" + closes_str
    )
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

@app.route("/shain")
def shain():
    return Response(SHAIN_HTML, mimetype="text/html")

@app.route("/kaigi")
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
