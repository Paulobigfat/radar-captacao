/* Radar de Captação — standalone browser frontend, no build tooling. */
'use strict';
const API = '/api';
const state = { view:'dashboard', buildingsPage:1, listingsPage:1, buildingSearch:'', buildingStatus:'', buildingNeighborhood:'', listingSearch:'', listingTransaction:'', filterPrecision:'', scanZone:'', scanSearch:'', scanTransaction:'', scanPage:1, lastFile:null };
const statuses = { new:'Novo', verify:'A verificar', prospecting:'Em prospecção', contacted:'Contato realizado', negotiating:'Em negociação', captured:'Captado', discarded:'Descartado' };
const precisionLabels = {full:'Endereço completo', partial:'Endereço parcial', approximate:'Aproximado', unknown:'Desconhecido'};
const $ = (selector, root=document) => root.querySelector(selector);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const brl = value => value == null ? '—' : new Intl.NumberFormat('pt-BR',{style:'currency',currency:'BRL',maximumFractionDigits:0}).format(value);
const num = value => new Intl.NumberFormat('pt-BR').format(value||0);
const stamp = value => value ? new Date(`${value}${value.endsWith('Z')?'':'Z'}`).toLocaleString('pt-BR',{dateStyle:'short', timeStyle:'short'}) : '—';
const placeName = b => b.name || (b.street && b.street_number ? `${b.street}, ${b.street_number}` : b.street || 'Edifício sem nome');
const streetLine = b => [b.street && !((b.name||'').toLowerCase() === (b.street||'').toLowerCase()) ? b.street : '',b.street_number||''].filter(Boolean).join(', ') || b.neighborhood || 'Endereço não divulgado';
const pill = name => `<span class="pill ${esc(name)}">${esc(statuses[name]||name||'—')}</span>`;
const precisionTag = name => `<span class="precision-tag ${esc(name)}">${name==='full'?'●':'◐'} ${esc(precisionLabels[name]||'Não informado')}</span>`;
const loading = () => `<div class="loading-screen"><span class="spinner"></span> Consultando dados...</div>`;
const empty = (heading, body, action) => `<div class="empty"><div class="empty-symbol">⌕</div><h3>${esc(heading)}</h3><p>${esc(body)}</p>${action ? `<button class="btn btn-primary" data-nav="import">Importar anúncios ↗</button>` : ''}</div>`;

async function request(path, options={}) {
  let response;
  // A timeout prevents an endless spinner when the browser cannot reach the API.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 12000);
  try { response = await fetch(`${API}${path}`, { ...options, signal: controller.signal }); }
  catch (err) {
    if (err?.name === 'AbortError') throw new Error('A API demorou para responder. Confira http://127.0.0.1:8000/api/health e o terminal.');
    throw new Error('Não foi possível conectar ao servidor. Abra o endereço http://127.0.0.1:8000 (não abra index.html como arquivo).');
  } finally { clearTimeout(timer); }
  const contentType=response.headers.get('content-type')||'';
  let data;
  if (contentType.includes('application/json')) { try {data=await response.json();} catch (_err) {data=null;} }
  if (!response.ok) {
    let detail=data?.detail || `Erro ${response.status}`;
    if (Array.isArray(detail)) detail=detail.map(item=>item.msg||'Dados inválidos').join(' · ');
    throw new Error(detail);
  }
  return data;
}
function toast(message, error=false) {
  const node=document.createElement('div'); node.className=`toast ${error?'error':''}`;node.textContent=message;
  $('#toast-container').append(node);setTimeout(()=>node.remove(),4200);
}
function header(eyebrow, title, description, buttons='') {
  return `<div class="page-head"><div><div class="eyebrow">${esc(eyebrow)}</div><h1>${esc(title)}</h1><p class="page-description">${esc(description)}</p></div><div class="page-actions">${buttons}</div></div>`;
}
function nav(view) {
  if (!['dashboard','buildings','listings','map','scan','import','sources','about'].includes(view)) return;
  state.view=view;
  document.querySelectorAll('[data-nav]').forEach(button => button.classList.toggle('active', button.classList.contains('nav-item') && button.dataset.nav === view));
  $('#sidebar').classList.remove('open');
  const labels={dashboard:'Visão geral',buildings:'Oportunidades',listings:'Anúncios',map:'Mapa',scan:'Varredura por zona',import:'Importar dados',sources:'Fontes automáticas',about:'Sobre o Radar'};
  $('#breadcrumb-current').textContent=labels[view];
  document.title=`${labels[view]} | Radar de Captação`;
  $('#main').innerHTML=loading();
  ({ dashboard:renderDashboard, buildings:renderBuildings, listings:renderListings, map:renderMap, scan:renderScan, import:renderImport, sources:renderSources, about:renderAbout })[view]().catch(handleError);
}
function handleError(err) { console.error(err); $('#main').innerHTML=header('ERRO','Não foi possível carregar','Ocorreu um problema ao obter os dados.')+empty('Falha na conexão',err.message,false);toast(err.message,true); }
function bindNavButtons(root=document) {
  root.addEventListener('click',e=>{
    const trigger=e.target.closest('[data-nav]');
    if (trigger){e.preventDefault(); nav(trigger.dataset.nav);}
  });
}

async function renderDashboard() {
  const d=await request('/dashboard');
  if (state.view!=='dashboard') return;
  const stats=[
    ['Edifícios identificados',d.buildings,'▤','Endereços agrupados'],
    ['Anúncios na base',d.total_listings,'≡',`${num(d.active_listings)} ativos`],
    ['Aguardando revisão',d.for_review,'◉','Correspondência a confirmar'],
    ['Captações em andamento',d.in_progress,'↗',`${num(d.captured)} concluídas`]
  ];
  const chartMax=Math.max(...d.neighborhoods.map(n=>n.count),1);
  const chartRows=d.neighborhoods.length?d.neighborhoods.map(n=>`<div class="chart-row"><div class="chart-label" title="${esc(n.name)}">${esc(n.name)}</div><div class="chart-track"><div class="chart-fill" style="width:${Math.round(n.count/chartMax*100)}%"></div></div><div class="chart-count">${num(n.count)}</div></div>`).join(''):empty('Sem dados para analisar','Importe anúncios para visualizar a distribuição por bairro.',true);
  const best=d.top_buildings.length?d.top_buildings.map(b=>`<div class="bldg-item" role="button" tabindex="0" data-building="${b.id}"><div class="building-marker">▥</div><div class="bldg-text"><strong>${esc(placeName(b))}</strong><small>${esc(b.neighborhood||b.city||'Sem bairro')} · ${num(b.listings_count)} anúncio(s)</small></div>${pill(b.status)}</div>`).join(''):empty('Nenhum edifício ainda','Comece importando sua primeira planilha.',true);
  $('#main').innerHTML=header('PAINEL DE INTELIGÊNCIA','Encontre onde estão as oportunidades.','Uma visão clara dos edifícios, anúncios e etapas de captação.',`<button class="btn btn-ghost" data-action="refresh">↻ Atualizar</button><button class="btn btn-primary" data-nav="sources">Fontes automáticas →</button>`)+
    `<section class="hero"><div class="hero-copy"><div class="hero-kicker">✦ DADOS QUE GERAM OPORTUNIDADES</div><h2>Menos tempo procurando.<br><span>Mais imóveis para captar.</span></h2><p>Pesquise páginas públicas de imobiliárias, agrupe endereços divulgados e organize oportunidades de captação.</p></div><div class="hero-orbit">⌖</div></section>`+
    `<section class="stats">${stats.map(s=>`<div class="stat"><div class="stat-row"><span class="stat-label">${esc(s[0])}</span><span class="stat-icon">${s[2]}</span></div><strong>${num(s[1])}</strong><div class="stat-foot">${esc(s[3])}</div></div>`).join('')}</section>`+
    `<section class="twocol"><div class="panel"><div class="panel-head"><div><h3>Edifícios em destaque</h3><p>Priorize locais com mais anúncios ativos</p></div><button class="panel-link" data-nav="buildings">Ver todos →</button></div>${best}</div><div class="panel"><div class="panel-head"><div><h3>Concentração por bairro</h3><p>Número de edifícios identificados</p></div></div><hr class="divider"><div class="chart">${chartRows}</div><div class="small-note">Indicadores baseados exclusivamente nos dados importados. Não representam todo o mercado imobiliário.</div></div></section>`;
}
function selected(value,current){return value===current?' selected':'';}
function optionsFor(items,value,all='Todos os bairros'){return `<option value="">${esc(all)}</option>${items.map(n=>`<option value="${esc(n)}"${selected(n,value)}>${esc(n)}</option>`).join('')}`;}
async function renderBuildings(){
  const params=new URLSearchParams({search:state.buildingSearch,status:state.buildingStatus,neighborhood:state.buildingNeighborhood,page:state.buildingsPage,limit:15,sort:'most_listings'});
  const [data,meta]=await Promise.all([request(`/buildings?${params}`),request('/meta')]);
  if(state.view!=='buildings')return;
  const rows=data.items.length?data.items.map(b=>`<tr class="click-row" data-building="${b.id}" tabindex="0"><td><span class="table-name">${esc(placeName(b))}</span><span class="table-sub">${esc(streetLine(b))}</span></td><td>${esc(b.neighborhood||'—')}</td><td><strong>${num(b.listings_count)}</strong><span class="table-sub">${num(b.units_estimated)} registros não duplicados</span></td><td>${b.min_price!=null?brl(b.min_price):'—'}</td><td>${precisionTag(b.precision)}</td><td>${pill(b.status)}</td><td><button class="btn btn-small" data-building="${b.id}">Detalhes ↗</button></td></tr>`).join(''):`<tr><td colspan="7">${empty('Nenhum edifício encontrado','Altere os filtros ou importe novos anúncios.',true)}</td></tr>`;
  $('#main').innerHTML=header('CENTRAL DE PROSPECÇÃO','Oportunidades de captação','Edifícios identificados, filtrados e prontos para análise.',`<button class="btn" data-action="export-buildings">↓ Exportar Excel</button><button class="btn btn-primary" data-action="manual">＋ Novo anúncio</button>`)+
    `<div class="toolbar"><input id="building-search" class="control search" placeholder="Buscar edifício, rua ou cidade..." value="${esc(state.buildingSearch)}" aria-label="Buscar edifícios"><select id="building-neighborhood" class="control">${optionsFor(meta.neighborhoods,state.buildingNeighborhood)}</select><select id="building-status" class="control"><option value="">Todos os status</option>${Object.entries(statuses).map(([k,v])=>`<option value="${k}"${selected(k,state.buildingStatus)}>${v}</option>`).join('')}</select><button class="btn btn-ghost" data-action="building-filter">Filtrar →</button></div>`+
    `<div class="table-panel"><div class="table-top"><h3>Lista de edifícios</h3><small>${num(data.total)} resultado(s)</small></div><div class="table-wrap"><table><thead><tr><th>Edifício</th><th>Bairro</th><th>Anúncios</th><th>A partir de</th><th>Precisão</th><th>Etapa</th><th></th></tr></thead><tbody>${rows}</tbody></table></div>${pager(data,'buildings')}</div>`;
}
function pager(data,target){return `<div class="pager"><span>Página ${data.page} de ${data.pages} · ${num(data.total)} registros</span><div class="pager-buttons"><button data-page-target="${target}" data-page="${Math.max(1,data.page-1)}" ${data.page<=1?'disabled':''}>← Anterior</button><button data-page-target="${target}" data-page="${Math.min(data.pages,data.page+1)}" ${data.page>=data.pages?'disabled':''}>Próxima →</button></div></div>`;}
async function renderListings(){
  const params=new URLSearchParams({search:state.listingSearch,transaction:state.listingTransaction,precision:state.filterPrecision,page:state.listingsPage,limit:20});
  const d=await request(`/listings?${params}`);
  if(state.view!=='listings')return;
  const rows=d.items.length?d.items.map(l=>`<tr><td><span class="table-name">${esc(l.building_name||l.street||'Imóvel sem endereço')}</span><span class="table-sub">${esc(l.neighborhood||'—')}, ${esc(l.city||'—')}</span></td><td><strong>${brl(l.price)}</strong><span class="table-sub">${l.transaction==='rent'?'Locação':'Venda'}</span></td><td>${l.area!=null?num(l.area)+' m²':'—'}<span class="table-sub">${l.bedrooms??'—'} dormitórios</span></td><td>${esc(l.source||'—')}</td><td>${precisionTag(l.precision)}</td><td>${l.duplicate_of?`<span class="pill verify" title="Mesmo prédio e unidade explicitamente informados">Duplicado #${l.duplicate_of}</span>`:'<span class="pill new">Registro</span>'}</td><td>${l.url?`<a class="panel-link" href="${esc(l.url)}" target="_blank" rel="noopener noreferrer">Ver ↗</a>`:''}</td></tr>`).join(''):`<tr><td colspan="7">${empty('Nenhum anúncio encontrado','Importe uma planilha para começar.',true)}</td></tr>`;
  $('#main').innerHTML=header('BASE DE DADOS','Anúncios imobiliários','Consulte registros importados e acompanhe sua origem e precisão.',`<button class="btn" data-action="export-listings">↓ Exportar Excel</button><button class="btn btn-primary" data-action="manual">＋ Novo anúncio</button>`)+
    `<div class="toolbar"><input class="control search" id="listing-search" placeholder="Buscar rua, bairro ou origem..." value="${esc(state.listingSearch)}"><select class="control" id="listing-transaction"><option value="">Venda e locação</option><option value="rent"${selected('rent',state.listingTransaction)}>Locação</option><option value="sale"${selected('sale',state.listingTransaction)}>Venda</option></select><select class="control" id="listing-precision"><option value="">Toda precisão</option>${Object.entries(precisionLabels).map(([k,v])=>`<option value="${k}"${selected(k,state.filterPrecision)}>${v}</option>`).join('')}</select><button class="btn btn-ghost" data-action="listing-filter">Filtrar →</button></div>`+
    `<div class="table-panel"><div class="table-top"><h3>Todos os anúncios</h3><small>${num(d.total)} resultado(s)</small></div><div class="table-wrap"><table><thead><tr><th>Imóvel / localização</th><th>Valor</th><th>Detalhes</th><th>Origem</th><th>Localização</th><th>Identificação</th><th>Link</th></tr></thead><tbody>${rows}</tbody></table></div>${pager(d,'listings')}</div>`;
}
function renderImport(){
  $('#main').innerHTML=header('CENTRAL DE IMPORTAÇÃO','Transforme dados em oportunidades','Traga seus anúncios autorizados e deixe o Radar organizar as informações.',`<button class="btn btn-primary" data-action="manual">＋ Cadastrar manualmente</button>`)+
    `<section class="import-grid"><div><div class="upload-drop" id="upload-drop"><div class="upload-icon">⇧</div><h3>Arraste seu arquivo até aqui</h3><p>Importe anúncios em massa. O sistema identifica endereços, agrupa edifícios e sinaliza correspondências que precisam de revisão.</p><input type="file" id="upload-file" accept=".csv,.xlsx,.json" hidden/><button class="btn btn-primary" data-action="choose-file">Selecionar arquivo ↗</button><div class="upload-hint">Formatos: .CSV, .XLSX, .JSON · Máximo 5 MB / 2.500 registros</div></div><div id="import-result"></div></div><div class="panel guide-panel"><h3>Como começar</h3><ol class="guide-list"><li><b>1</b><span>Obtenha uma planilha de uma fonte que permita a utilização dos dados para essa finalidade.</span></li><li><b>2</b><span>Use colunas como cidade, bairro, rua, número, edifício, preço, link e finalidade.</span></li><li><b>3</b><span>Envie o arquivo. Endereços incompletos não serão tratados como identificações exatas.</span></li><li><b>4</b><span>Revise os edifícios encontrados e mova cada oportunidade pelo funil de captação.</span></li></ol><div class="guide-bottom">Precisa de um exemplo?<br><a href="/static/../examples/modelo_importacao.csv" id="download-example" class="panel-link">Baixar modelo CSV ↓</a><br><a href="#" id="import-demo" class="panel-link">Carregar dados fictícios de demonstração ↗</a></div></div></section>`;
  $('#download-example').href='/api/example/csv';
  const drop=$('#upload-drop');
  drop.addEventListener('dragover',event=>{event.preventDefault();drop.classList.add('dragging');});
  drop.addEventListener('dragleave',()=>drop.classList.remove('dragging'));
  drop.addEventListener('drop',event=>{event.preventDefault();drop.classList.remove('dragging');if(event.dataTransfer.files.length)uploadFile(event.dataTransfer.files[0]);});
  $('#upload-file').addEventListener('change',event=>{if(event.target.files.length)uploadFile(event.target.files[0]);});
  $('#import-demo').addEventListener('click',async event=>{event.preventDefault();try{const response=await fetch('/api/example/demo');if(!response.ok)throw new Error('Exemplo não disponível');const data=await response.json();const result=await request('/import/json',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});showImportResult(result);toast('Dados demonstrativos carregados!');}catch(error){toast(error.message,true);}});
}
async function uploadFile(file){
  const resultEl=$('#import-result');
  if(!resultEl) return;
  resultEl.innerHTML=`<div class="result"><span class="spinner"></span> Processando ${esc(file.name)}...</div>`;
  try{const form=new FormData();form.append('file',file);const result=await request('/import/file',{method:'POST',body:form});showImportResult(result);toast('Importação finalizada.');}
  catch(error){resultEl.innerHTML=`<div class="result error"><strong>Erro na importação</strong>${esc(error.message)}</div>`;toast(error.message,true);}
}
function showImportResult(result){
  const target=$('#import-result');if(!target)return;
  target.innerHTML=`<div class="result"><strong>✓ Importação processada</strong><p>${num(result.created)} novo(s) anúncio(s) · ${num(result.updated)} atualizado(s) · ${num(result.duplicates)} possível(is) duplicidade(s) confirmada(s) por unidade · ${num(result.failed)} erro(s)</p>${result.errors.length?`<details><summary>Ver erros</summary>${result.errors.map(e=>`<p>Linha ${num(e.row)}: ${esc(e.message)}</p>`).join('')}</details>`:''}<button class="btn btn-primary" data-nav="buildings">Explorar edifícios →</button></div>`;
}
async function renderSources(){
  const data=await request('/sources');
  if(state.view!=='sources') return;
  const summary = data.auto_sync ? 'A sincronização é verificada aproximadamente a cada 30 segundos enquanto o Radar está aberto.' : 'O agendador está desativado neste ambiente; utilize Sincronizar agora.';
  const rows=data.items.length ? data.items.map(src=>`<div class="source-card">
    <div class="source-info"><strong>${esc(src.name)}</strong><span class="table-sub">${src.kind==='file'?'Arquivo local':src.kind==='web'?'Varredura de site público':'Feed HTTPS'} · ${esc(src.location)}</span><span class="table-sub">A cada ${num(src.interval_minutes)} min · Última execução: ${stamp(src.last_run_at)}</span><span class="table-sub">${src.last_error?`⚠ ${esc(src.last_error)}`:src.last_result==='ok'?'✓ Última atualização concluída':src.last_result==='partial'?'⚠ Nenhum anúncio identificado ou execução parcial — consulte Histórico':'Aguardando a primeira atualização'}</span></div>
    <div class="source-actions"><span class="pill ${src.last_result==='error'?'verify':'new'}">${src.enabled?'Ativa':'Pausada'}</span><button class="btn btn-small btn-primary" data-action="source-run" data-id="${src.id}" data-kind="${esc(src.kind)}">↻ Sincronizar agora</button><button class="btn btn-small" data-action="source-history" data-id="${src.id}">Histórico</button><button class="btn btn-small" data-action="source-toggle" data-id="${src.id}" data-enabled="${src.enabled}">${src.enabled?'Pausar':'Ativar'}</button><button class="btn btn-small btn-danger" data-action="source-delete" data-id="${src.id}">Excluir</button></div>
  </div>`).join('') : empty('Nenhuma fonte cadastrada','Adicione o endereço HTTPS público de uma imobiliária ou um feed de dados.',false);
  $('#main').innerHTML=header('SINCRONIZAÇÃO','Fontes automáticas','Cadastre páginas públicas de imobiliárias e acompanhe os anúncios encontrados.',`<button class="btn" data-nav="import">Importar manualmente →</button>`)+
    `<div class="notice"><strong>Como funciona:</strong> a varredura consulta HTML e sitemaps públicos do domínio cadastrado, respeita robots.txt e não contorna CAPTCHA/login. Alguns sites carregam anúncios por JavaScript e podem não apresentar dados extraíveis. Não há garantia de cobertura completa nem de disponibilidade atual. ${esc(summary)}</div>`+
    `<section class="sources-layout"><div class="panel sources-panel"><div class="panel-head"><div><h3>Fontes configuradas</h3><p>${num(data.items.length)} fonte(s) · dados mantidos no banco local</p></div></div>${rows}<div id="source-feedback"></div></div>
    <form class="panel sources-form" id="source-form"><h3>Adicionar uma fonte</h3><p class="page-description">Para pesquisar anúncios de uma imobiliária, escolha "Site público" e cole a página de imóveis ou o endereço principal HTTPS do site.</p>
    <div class="field"><label for="source-name">Nome da fonte</label><input id="source-name" name="name" required maxlength="100" placeholder="Ex.: Parceiro imobiliário"></div>
    <div class="field"><label for="source-kind">Tipo de fonte</label><select id="source-kind" name="kind"><option value="web">Site público de imobiliária (HTML + sitemap)</option><option value="file">Arquivo monitorado (local)</option><option value="https">Feed CSV/JSON HTTPS</option></select></div>
    <div class="field"><label for="source-location">Arquivo / URL</label><input id="source-location" name="location" required placeholder="https://www.exemplo.com.br/imoveis"></div>
    <div class="field"><label for="source-interval">Intervalo de atualização (minutos)</label><input id="source-interval" name="interval_minutes" type="number" min="15" max="10080" value="360"></div>
    <label class="source-check" id="source-rights-wrap" style="display:none"><input type="checkbox" name="rights_confirmed"> Confirmo que esse feed/arquivo foi disponibilizado para esse uso.</label>
    <button class="btn btn-primary" type="submit">＋ Adicionar fonte</button>
    <div class="small-note">A pesquisa pública não exige API nem login, mas respeita robots.txt e interrompe acesso negado. Use sempre uma URL HTTPS final. Endereços ocultos não podem ser recuperados; páginas dinâmicas podem requerer integração específica. Para testar um feed local, use <code>exemplo_autorizado.json</code>.</div></form></section>`;
}

async function renderScan(){
  const params=new URLSearchParams({zone:state.scanZone,search:state.scanSearch,transaction:state.scanTransaction,page:state.scanPage,limit:50});
  const data=await request(`/reports/availability?${params}`);
  if(state.view!=='scan')return;
  const rows=data.items.length?data.items.map(item=>`<tr>
    <td><strong>${esc(item.zone)}</strong><span class="table-sub">${esc(item.neighborhood||'Bairro não divulgado')}</span></td>
    <td><span class="table-name">${esc(item.street?`${item.street}${item.street_number?', '+item.street_number:''}`:'Endereço não divulgado')}</span><span class="table-sub">${esc(item.city||'—')}</span></td>
    <td>${esc(item.property_type||'Imóvel')}<span class="table-sub">${item.transaction==='rent'?'Locação':'Venda'}</span></td>
    <td><strong>${brl(item.price)}</strong></td>
    <td>${precisionTag(item.precision)}</td>
    <td>${esc(item.source)}</td>
    <td>${item.url?`<a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">Anúncio ↗</a>`:'—'}</td>
  </tr>`).join(''):`<tr><td colspan="7">${empty('Nenhum anúncio encontrado','Cadastre um site público na seção Fontes automáticas e execute a varredura.',false)}</td></tr>`;
  const zonelist=optionsFor(data.zones,state.scanZone,'Todas as zonas');
  $('#main').innerHTML=header('PESQUISA PÚBLICA','Anúncios por zona e endereço','Unidades anunciadas em páginas pesquisadas; endereços e disponibilidade sujeitos a confirmação.',`<button class="btn" data-action="scan-export">↓ Exportar Excel</button><button class="btn btn-primary" data-nav="sources">＋ Cadastrar site</button>`)+
    `<div class="notice"><strong>Precisão:</strong> "Zona" usa o arquivo configurável <code>config/zonas.json</code>. Bairros fora do mapa aparecem como "Não classificada". A varredura não identifica endereços que não estejam públicos.</div>`+
    `<div class="toolbar"><input id="scan-search" class="control search" placeholder="Rua, edifício ou bairro..." value="${esc(state.scanSearch)}" aria-label="Buscar anúncios"><select class="control" id="scan-zone">${zonelist}</select><select class="control" id="scan-transaction"><option value="">Venda e locação</option><option value="rent"${selected('rent',state.scanTransaction)}>Locação</option><option value="sale"${selected('sale',state.scanTransaction)}>Venda</option></select><button class="btn btn-primary" data-action="scan-filter">Filtrar</button></div>`+
    `<div class="panel table-panel"><div class="panel-head"><h3>${num(data.total)} anúncio(s) identificados</h3><p>Página ${data.page} de ${data.pages}</p></div><div class="table-wrap"><table><thead><tr><th>Zona / bairro</th><th>Endereço divulgado</th><th>Imóvel</th><th>Valor</th><th>Precisão</th><th>Origem</th><th>Link</th></tr></thead><tbody>${rows}</tbody></table></div></div>`+
    `<div class="pagination"><button class="btn btn-small" data-action="scan-prev"${data.page<=1?' disabled':''}>← Anterior</button><span>${data.page} / ${data.pages}</span><button class="btn btn-small" data-action="scan-next"${data.page>=data.pages?' disabled':''}>Próxima →</button></div>`;
}

async function showSourceHistory(id){
  try {
    const data=await request(`/sources/${id}/runs`);
    const target=$('#source-feedback');if(!target)return;
    const statuses={running:'Em execução',ok:'Concluída',partial:'Incompleta / nenhum anúncio',error:'Falha'};
    target.innerHTML=`<div class="result" id="history-${id}"><strong>Diagnóstico da varredura</strong>${data.items.length?data.items.map(r=>`<p><strong>${esc(statuses[r.status]||r.status)}</strong> — ${stamp(r.started_at)}<br>${num(r.created)} novos / ${num(r.updated)} atualizados / ${num(r.failed)} inválidos<br>${esc(r.message)}</p>`).join(''):'<p>Nenhuma sincronização realizada.</p>'}${data.items.some(r=>r.status==='running')?'<small>Atualização automática do histórico enquanto a varredura está em execução.</small>':''}</div>`;
    if(data.items.some(r=>r.status==='running')){
      setTimeout(()=>{if(state.view==='sources' && $('#history-'+id))showSourceHistory(id);},2500);
    }
  }catch(e){toast(e.message,true);}
}

async function renderMap(){
  const data=await request('/buildings?limit=100&page=1');
  if(state.view!=='map')return;
  const coords=data.items.filter(x=>typeof x.latitude==='number'&&typeof x.longitude==='number');
  $('#main').innerHTML=header('VISUALIZAÇÃO GEOGRÁFICA','Mapa de oportunidades','Exibe somente edifícios com coordenadas fornecidas e confiáveis.',`<button class="btn" data-nav="buildings">Ver lista de edifícios →</button>`)+
    `<div class="panel">${coords.length?`<div class="map-panel"><div id="map-canvas"></div></div><div class="small-note">Visualização via OpenStreetMap. O mapa requer acesso à internet. Coordenadas são trazidas pelas fontes importadas, não inferidas pelo Radar.</div>`:empty('Nenhuma coordenada disponível','Importe anúncios autorizados que contenham latitude e longitude confirmadas. O Radar não estima números de edifícios ou coordenadas.',false)}</div>`;
  if(coords.length) await createMap(coords);
}
async function createMap(buildings){
  if(!document.querySelector('#leaflet-style')){
    const style=document.createElement('link');style.id='leaflet-style';style.rel='stylesheet';style.href='https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';document.head.appendChild(style);
  }
  if(!window.L){
    try {await new Promise((resolve,reject)=>{const s=document.createElement('script');s.src='https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';s.onload=resolve;s.onerror=reject;document.head.appendChild(s);});}
    catch(_err){$('#map-canvas').innerHTML=empty('Mapa indisponível offline','A lista de oportunidades continua acessível sem internet.',false);return;}
  }
  const map=L.map('map-canvas').setView([buildings[0].latitude,buildings[0].longitude],12);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{attribution:'© OpenStreetMap contributors',maxZoom:18}).addTo(map);
  const markers=[];
  buildings.forEach(b=>{
    const marker=L.marker([b.latitude,b.longitude]).addTo(map);
    const details=document.createElement('div');
    const title=document.createElement('strong');title.textContent=placeName(b);details.appendChild(title);
    const line=document.createElement('p');line.textContent=`${b.listings_count} anúncios · ${b.neighborhood}`;details.appendChild(line);
    const button=document.createElement('button');button.textContent='Abrir detalhes';button.onclick=()=>openBuilding(b.id);details.appendChild(button);
    marker.bindPopup(details);markers.push(marker);
  });
  if(markers.length>1){map.fitBounds(L.featureGroup(markers).getBounds().pad(.18));}
}
function renderAbout(){
  $('#main').innerHTML=header('SOBRE O PRODUTO','Inteligência imobiliária, sem complicações','Um radar local para organizar anúncios públicos e fontes de dados em oportunidades.')+
  `<div class="hero"><div class="hero-copy"><div class="hero-kicker">RADAR DE CAPTAÇÃO · V0.3.1</div><h2>Uma plataforma pensada para <span>identificar oportunidades reais.</span></h2><p>Os dados permanecem na instalação local. Sites públicos (respeitando robots.txt) e feeds podem ser atualizados enquanto o aplicativo está aberto.</p></div><div class="hero-orbit">⌖</div></div>`+
  `<div class="about-grid"><div class="about-card"><div class="big-icon">▤</div><h3>Identificação conservadora</h3><p>Agrupa endereços completos e nome de prédio com bairro. Nunca inventa o número de um imóvel.</p></div><div class="about-card"><div class="big-icon">≡</div><h3>Controle de captações</h3><p>Status, observações, histórico e registros associados ajudam a organizar o acompanhamento.</p></div><div class="about-card"><div class="big-icon">↧</div><h3>Seus dados, suas regras</h3><p>Arquivos CSV, Excel e JSON, varredura limitada de páginas públicas e armazenamento local SQLite.</p></div></div>`+
  `<div class="notice"><strong>Importante:</strong> há coleta de HTML público para sites com acesso permitido por robots.txt, sem contornar bloqueios. Utilize somente informações obtidas de fontes com permissão compatível. Endereços parciais não identificam um prédio com segurança. O MVP não possui contas, login ou isolamento entre empresas — não exponha diretamente na internet.</div>`;
}
async function openBuilding(id){
  try{
    const b=await request(`/buildings/${id}`);
    const existing=$('#modal-root');
    const listingCards=b.listings.length?b.listings.map(l=>`<div class="listing-card"><div class="listing-card-top"><strong>${brl(l.price)}</strong><span>${l.transaction==='rent'?'Locação':'Venda'}</span></div><div class="listing-card-bottom"><span>${l.area??'—'} m²</span><span>${l.bedrooms??'—'} dorm.</span><span>${esc(l.source)}</span>${l.duplicate_of?`<span>Duplicado #${l.duplicate_of}</span>`:''}${l.url?`<a href="${esc(l.url)}" target="_blank" rel="noopener noreferrer">Anúncio original ↗</a>`:''}</div></div>`).join(''):'<p class="page-description">Nenhum anúncio associado.</p>';
    existing.innerHTML=`<div class="modal-backdrop" id="details-backdrop"><section class="drawer" role="dialog" aria-modal="true" aria-label="Detalhes do edifício"><div class="drawer-head"><div><div class="eyebrow">OPORTUNIDADE #${b.id}</div><h2>${esc(placeName(b))}</h2><p>${esc(streetLine(b))} · ${esc(b.neighborhood)} / ${esc(b.city)}</p></div><button class="icon-btn" data-close aria-label="Fechar">×</button></div><div class="details-stats"><div class="details-stat"><strong>${num(b.listings_count)}</strong><small>Anúncios ativos</small></div><div class="details-stat"><strong>${num(b.units_estimated)}</strong><small>Registros únicos¹</small></div><div class="details-stat"><strong>${Math.round(b.confidence*100)}%</strong><small>Confiança da associação</small></div></div><div>${precisionTag(b.precision)} <span class="pill" style="margin-left:8px">${esc(b.precision==='full'?'Endereço informado':'Verificação necessária')}</span></div><h3>Etapa de captação</h3><div class="status-save-row"><div class="field"><select id="detail-status">${Object.entries(statuses).map(([k,v])=>`<option value="${k}"${selected(k,b.status)}>${v}</option>`).join('')}</select></div><button class="btn btn-primary" id="save-status" data-id="${b.id}">Salvar etapa</button></div><h3>Anotações internas</h3><div class="field"><textarea id="detail-notes" placeholder="Registre a estratégia de abordagem, responsáveis e observações...">${esc(b.notes)}</textarea></div><button class="btn btn-small" id="save-notes" data-id="${b.id}">Salvar observações</button><h3>Anúncios associados (${num(b.listings.length)})</h3>${listingCards}<h3>Histórico de atividades</h3><div class="field"><textarea rows="2" id="activity-text" placeholder="Ex.: confirmar prédio com o responsável..." style="min-height:65px"></textarea></div><button class="btn btn-small btn-primary" data-id="${b.id}" id="add-activity">＋ Adicionar registro</button><div style="margin-top:20px">${b.activities.length?b.activities.map(a=>`<div class="activity"><small>${stamp(a.created_at)} · ${esc(a.kind)}</small><p>${esc(a.message)}</p></div>`).join(''):'<p class="page-description">Nenhuma atividade registrada.</p>'}</div><div class="small-note">¹ Registros sem duplicidade comprovada. Sem identificação da unidade, anúncios distintos podem representar o mesmo imóvel.</div></section></div>`;
    document.body.style.overflow='hidden';
    $('[data-close]',existing)?.focus();
  }catch(error){toast(error.message,true);}
}
function closeModal(){ $('#modal-root').replaceChildren();document.body.style.overflow=''; }
function manualModal(){
  const fields=[['source','Origem','text','Cadastro manual'],['external_id','Código externo','text',''],['city','Cidade','text','Porto Alegre'],['neighborhood','Bairro','text',''],['street','Rua','text',''],['street_number','Número','text',''],['building_name','Edifício','text',''],['unit_ref','Unidade (se conhecida)','text',''],['price','Preço (R$)','number',''],['area','Área (m²)','number',''],['bedrooms','Dormitórios','number',''],['url','Link do anúncio','url','']];
  $('#modal-root').innerHTML=`<div class="modal-backdrop" id="details-backdrop"><form id="manual-form" class="modal-card" role="dialog" aria-modal="true" aria-label="Cadastrar anúncio"><div class="drawer-head"><div><div class="eyebrow">NOVO REGISTRO</div><h2>Adicionar anúncio</h2><p>Preencha somente dados confirmados. Não invente endereços.</p></div><button class="icon-btn" data-close type="button" aria-label="Fechar">×</button></div><div class="form-grid">${fields.map(([id,label,type,placeholder])=>`<div class="field"><label for="m-${id}">${esc(label)}</label><input id="m-${id}" name="${id}" type="${type}" placeholder="${esc(placeholder)}" ${id==='city'?'required':''}></div>`).join('')}</div><div class="field"><label for="m-transaction">Finalidade</label><select name="transaction" id="m-transaction"><option value="rent">Locação</option><option value="sale">Venda</option></select></div><div class="modal-actions"><button class="btn" data-close type="button">Cancelar</button><button class="btn btn-primary" type="submit">Cadastrar anúncio</button></div></form></div>`;
  document.body.style.overflow='hidden';
  $('#m-city')?.focus();
}
async function saveBuilding(id,key,value){try{await request(`/buildings/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({[key]:value})});toast('Informação atualizada.');await openBuilding(id);if(['buildings','dashboard'].includes(state.view)) { /* Refresh underlying list after drawer is dismissed. */ }}catch(error){toast(error.message,true);}}
function download(path){window.location.href=path;}
// Page events stay on the document because each view is rebuilt after API requests.
document.addEventListener('click',async event=>{
  const b=event.target.closest('button,a,[data-building]');
  if(!b)return;
  if(b.dataset.building){event.preventDefault();await openBuilding(Number(b.dataset.building));return;}
  if(b.hasAttribute('data-close')){event.preventDefault();closeModal();return;}
  if(b.dataset.pageTarget){if(b.dataset.pageTarget==='buildings'){state.buildingsPage=Number(b.dataset.page);nav('buildings');}else{state.listingsPage=Number(b.dataset.page);nav('listings');}return;}
  if(b.id==='save-status'){await saveBuilding(Number(b.dataset.id),'status',$('#detail-status').value);return;}
  if(b.id==='save-notes'){await saveBuilding(Number(b.dataset.id),'notes',$('#detail-notes').value);return;}
  if(b.id==='add-activity'){
    const value=$('#activity-text').value.trim();if(value.length<2){toast('Descreva a atividade.',true);return;}
    try{await request(`/buildings/${b.dataset.id}/activities`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:value})});toast('Atividade registrada.');await openBuilding(Number(b.dataset.id));}catch(error){toast(error.message,true);}return;
  }
  if(b.id==='mobile-toggle'){$('#sidebar').classList.toggle('open');return;}
  switch(b.dataset.action){
    case 'scan-filter':state.scanSearch=$('#scan-search').value.trim();state.scanZone=$('#scan-zone').value;state.scanTransaction=$('#scan-transaction').value;state.scanPage=1;nav('scan');return;
    case 'scan-prev':state.scanPage=Math.max(1,state.scanPage-1);nav('scan');return;
    case 'scan-next':state.scanPage++;nav('scan');return;
    case 'scan-export':window.location.assign('/api/reports/availability/export?'+new URLSearchParams({zone:state.scanZone,transaction:state.scanTransaction,format:'xlsx'}));return;
    case 'source-run': {
      b.disabled=true;b.textContent='Sincronizando...';
      try{if(b.dataset.kind==='web'){await request(`/sources/${b.dataset.id}/start`,{method:'POST'});toast('Varredura iniciada. Acompanhe o diagnóstico nesta tela.');await renderSources();await showSourceHistory(b.dataset.id);}else{const r=await request(`/sources/${b.dataset.id}/run`,{method:'POST'});toast(r.status==='error'?`Falha: ${r.message}`:`Sincronização: ${r.created} novo(s), ${r.updated} atualizado(s)`,r.status==='error');nav('sources');}}
      catch(e){toast(e.message,true);b.disabled=false;b.textContent='↻ Sincronizar agora';}return;
    }
    case 'source-history':await showSourceHistory(b.dataset.id);return;
    case 'source-toggle': {
      try {await request(`/sources/${b.dataset.id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:b.dataset.enabled!=='true'})});nav('sources');}
      catch(e){toast(e.message,true);}return;
    }
    case 'source-delete': {
      if(!confirm('Excluir esta fonte e seu histórico? Os anúncios já importados serão mantidos.'))return;
      try{await request(`/sources/${b.dataset.id}`,{method:'DELETE'});toast('Fonte excluída; anúncios preservados.');nav('sources');}
      catch(e){toast(e.message,true);}return;
    }
    case 'refresh':nav('dashboard');break;
    case 'manual':manualModal();break;
    case 'choose-file':$('#upload-file')?.click();break;
    case 'export-buildings':download('/api/export/buildings?format=xlsx');break;
    case 'export-listings':download('/api/export/listings?format=xlsx');break;
    case 'building-filter':state.buildingSearch=$('#building-search').value.trim();state.buildingNeighborhood=$('#building-neighborhood').value;state.buildingStatus=$('#building-status').value;state.buildingsPage=1;nav('buildings');break;
    case 'listing-filter':state.listingSearch=$('#listing-search').value.trim();state.listingTransaction=$('#listing-transaction').value;state.filterPrecision=$('#listing-precision').value;state.listingsPage=1;nav('listings');break;
  }
});
document.addEventListener('submit',async e=>{
  if(e.target.id==='source-form'){
    e.preventDefault();
    const form=e.target;const values=Object.fromEntries(new FormData(form).entries());
    const payload={...values,interval_minutes:Number(values.interval_minutes),rights_confirmed:values.rights_confirmed==='on'};
    const submit=form.querySelector('[type=submit]');submit.disabled=true;
    try{await request('/sources',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});toast('Fonte adicionada. Clique em Sincronizar agora para importar.');nav('sources');}
    catch(error){toast(error.message,true);submit.disabled=false;}
    return;
  }
  if(e.target.id!=='manual-form')return;
  e.preventDefault();
  const data=Object.fromEntries(new FormData(e.target).entries());
  for(const key in data)if(data[key]==='')delete data[key];
  try{await request('/listings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});toast('Anúncio cadastrado com sucesso!');closeModal();nav('buildings');}
  catch(error){toast(error.message,true);}
});
document.addEventListener('change',event=>{
  if(event.target.id==='source-kind'){
    const isFeed=event.target.value!=='web';
    const wrap=$('#source-rights-wrap');
    if(wrap){wrap.style.display=isFeed?'':'none';wrap.querySelector('input').required=isFeed;}
    const location=$('#source-location');
    if(location)location.placeholder=event.target.value==='file'?'exemplo_autorizado.json':'https://www.exemplo.com.br/imoveis';
  }
});
document.addEventListener('keydown',event=>{
  if(event.key==='Escape'&&$('#modal-root').children.length)closeModal();
  if(event.key==='Enter'){
    if(event.target.id==='building-search'){$('[data-action="building-filter"]')?.click();}
    if(event.target.id==='scan-search'){$('[data-action="scan-filter"]')?.click();}
    if(event.target.id==='listing-search'){$('[data-action="listing-filter"]')?.click();}
    if(event.target.matches('tr.click-row')){const id=event.target.dataset.building;if(id)openBuilding(Number(id));}
  }
});
document.addEventListener('click',event=>{if(event.target.id==='details-backdrop')closeModal();});
bindNavButtons();
nav('dashboard');
