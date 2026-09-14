#!/usr/bin/env python3
"""Build a single self-contained preview page (for sharing / artifact publishing)."""
import json, os, html, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build, meta

rows = build.load()
by_country, by_sector = {}, {}
for n in rows:
    by_country.setdefault(n.get("c") or "XXX", []).append(n)
    for d in n.get("cpv", []):
        by_sector.setdefault(d, []).append(n)

data = [[n["id"], n["t"], n.get("c", ""), n.get("cpv", []), n["d"][:10],
         n.get("b", ""), n.get("nat", "")] for n in rows]

sec_index = "".join(
    f'<a href="#" data-s="{d}"><i>{html.escape(meta.cpv_label(d))}</i><u>{len(v)}</u></a>'
    for d, v in sorted(by_sector.items(), key=lambda kv: (-len(kv[1]), kv[0])))

cnt_opts = "".join(f'<option value="{c}">{html.escape(meta.country_name(c))}</option>'
                   for c in sorted(by_country, key=lambda k: meta.country_name(k)))
sec_opts = "".join(f'<option value="{d}">{html.escape(meta.cpv_label(d))}</option>'
                   for d in sorted(by_sector))

page = f"""<title>Bidledger</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&family=Newsreader:opsz,wght@6..72,500;6..72,600&display=swap">
<style>{build.CSS}
.demo{{background:var(--seal-soft);border:1px solid var(--line);padding:11px 16px;
font-size:13px;color:var(--mut);margin:22px 0 0;border-radius:2px}}
.demo b{{color:var(--ink)}}
</style>
<header class="mast"><div class="wrap"><a class="logo" href="#">Tender<em>Pulse</em></a>
<nav><a href="#sectors">Sectors</a><a href="#alerts">Follow updates</a>
<a href="https://ted.europa.eu/" target="_blank" rel="noopener">Source: TED</a></nav></div></header>

<div class="wrap">
<h1>Every open EU public tender, in one place.</h1>
<p class="sub">Calls for tenders from across the European Union, pulled from the Official
Journal every morning and made searchable. Free, no account, no dashboard to learn.</p>

<div class="demo"><b>Preview build.</b> {len(rows)} real notices, fetched live from the
TED API. The production site carries the full daily feed &mdash; roughly 33,000 open
calls at any moment &mdash; with a page per notice, per sector and per country.</div>

<div class="band">
<div><b id="n1">{len(rows)}</b><span>open tenders</span></div>
<div><b>{len(by_country)}</b><span>countries</span></div>
<div><b>{len(by_sector)}</b><span>sectors</span></div>
<div><b>05:17</b><span>UTC daily refresh</span></div>
</div>

<label for="q" style="position:absolute;left:-9999px">Search tenders</label>
<input id="q" type="search" placeholder="Search &mdash; software, catering, road works, monitors&hellip;" autocomplete="off">
<div class="filters">
<select id="fc" aria-label="Country"><option value="">All countries</option>{cnt_opts}</select>
<select id="fs" aria-label="Sector"><option value="">All sectors</option>{sec_opts}</select>
<select id="fn" aria-label="Contract type"><option value="">Works, supplies and services</option>
<option value="works">Works</option><option value="supplies">Supplies</option>
<option value="services">Services</option></select>
</div>

<h2 id="list-h">Closing soonest</h2>
<div id="res"></div>

<div class="note" id="alerts"><h2>Follow updates</h2>
<p>The production site provides free RSS feeds, CSV exports and a JSON API.</p>
<a class="btn" href="#">See update options</a></div>

<h2 id="sectors">Browse by sector</h2>
<div class="index">{sec_index}</div>
</div>

<footer><div class="wrap">
Data source: <a href="https://ted.europa.eu/" target="_blank" rel="noopener">Tenders
Electronic Daily</a>, the official journal of EU public procurement, re-used under the
European Commission's open data policy. Bidledger is an independent service and is not
affiliated with the European Union. Every notice links back to the authoritative text.
</div></footer>

<script>
var D={json.dumps(data, ensure_ascii=False, separators=(',', ':'))};
var CN={json.dumps({k: meta.country_name(k) for k in by_country}, ensure_ascii=False)};
var CP={json.dumps({d: meta.cpv_label(d) for d in by_sector}, ensure_ascii=False)};
function esc(s){{return String(s).replace(/[&<>"]/g,function(c){{
return {{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}}[c]}})}}
function days(d){{return Math.ceil((new Date(d)-new Date())/864e5)}}
function fmt(d){{return new Date(d).toLocaleDateString('en-GB',
{{day:'2-digit',month:'short',year:'numeric'}})}}
function row(n){{var k=days(n[4]);
return '<div class="row"><div class="ref">'+n[0]+'</div>'+
'<div class="ttl"><a href="https://ted.europa.eu/en/notice/-/detail/'+n[0]+
'" target="_blank" rel="noopener">'+esc(n[1])+'</a>'+
'<div class="meta">'+esc(CN[n[2]]||n[2])+' &middot; '+esc(n[5].slice(0,64))+'</div>'+
'<div style="margin-top:6px">'+n[3].slice(0,2).map(function(c){{
return '<span class="chip">'+esc((CP[c]||c).slice(0,26))+'</span>'}}).join('')+'</div></div>'+
'<div class="when'+(k<=7?' soon':'')+'"><b>'+fmt(n[4])+'</b>'+k+' days left</div></div>'}}
function run(){{
var t=document.getElementById('q').value.trim().toLowerCase();
var c=document.getElementById('fc').value,s=document.getElementById('fs').value,
    nt=document.getElementById('fn').value;
var w=t?t.split(/\\s+/):[],out=[];
for(var i=0;i<D.length;i++){{var n=D[i];
 if(c&&n[2]!==c)continue; if(s&&n[3].indexOf(s)<0)continue; if(nt&&n[6]!==nt)continue;
 if(w.length){{var h=(n[1]+' '+n[5]).toLowerCase(),ok=1;
  for(var j=0;j<w.length;j++){{if(h.indexOf(w[j])<0){{ok=0;break}}}}
  if(!ok)continue}}
 out.push(n)}}
out.sort(function(a,b){{return a[4]<b[4]?-1:1}});
document.getElementById('list-h').textContent =
  (t||c||s||nt) ? out.length+' matching tender'+(out.length===1?'':'s') : 'Closing soonest';
document.getElementById('res').innerHTML = out.length ? out.map(row).join('') :
  '<p class="sub" style="padding:18px 0">Nothing open matches that right now. '+
  'On the full feed this search runs across every live notice in the Union.</p>';
}}
['q','fc','fs','fn'].forEach(function(id){{
  var el=document.getElementById(id);
  el.addEventListener('input',run); el.addEventListener('change',run)}});
document.querySelectorAll('.index a').forEach(function(a){{
  a.addEventListener('click',function(e){{e.preventDefault();
    document.getElementById('fs').value=a.getAttribute('data-s');
    document.getElementById('q').value='';run();
    document.getElementById('list-h').scrollIntoView({{behavior:'smooth'}})}})}});
run();
</script>"""

out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "preview.html")
open(out, "w", encoding="utf-8").write(page)
print("wrote", out, os.path.getsize(out), "bytes")
