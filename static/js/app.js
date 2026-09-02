// ══════════════════════════════════════════════════════
//  共享数据层
// ══════════════════════════════════════════════════════
const S = {
  // 来自 1688 抓取
  scrapedTaskId: null,
  scrapedFolder: null,
  scrapedImages: [],       // {path, url}
  scrapedAllImages: [],    // 全部采集图片路径

  // 来自分析
  anaTaskId: null,
  anaReport: null,
  anaStrategies: null,
  productImageFiles: [],

  // 视频
  scriptTaskId: null,
  scriptPath: null,
  vidScriptSegments: null,   // 口播分段数据，用于精铺模式分镜叠加文案
  audioPath: null,
  srtPath: null,
  uploadedSrt: '',
  _genImages: [],  // 生图 URL 缓存，供图库侧边栏使用

  // 通用
  productTitle: '',
  productPoints: '',
  currentTab: 'tabScrape',
};

const A8_API = '/api/v1';

// ══════════════════════════════════════════════════════
//  Tab 切换
// ══════════════════════════════════════════════════════
document.querySelectorAll('#navTabs .nav-tab').forEach(t => {
  t.addEventListener('click', () => switchTab(t.dataset.tab));
});
function switchTab(tabId) {
  S.currentTab = tabId;
  document.querySelectorAll('#navTabs .nav-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tabId));
  document.querySelectorAll('.tab-content').forEach(c => c.style.display = c.id === tabId ? '' : 'none');
  updateFlowHint();
  if (tabId === 'tabVideo') { }
  if (tabId === 'tabHistory') { histPage = 0; loadHistory(); }
}
function updateFlowHint() {
  const steps = { tabScrape: 0, tabAnalysis: 1, tabDirectStrategy: 2, tabImageGen: 3, tabVideo: 4 };
  const cur = steps[S.currentTab] ?? 0;
  const h = document.getElementById('flowHint');
  const labels = ['📦 1688', '📊 分析', '🎯 策略', '🖼️ 生图', '🎬 视频'];
  h.innerHTML = labels.map((l, i) => {
    let cls = '';
    if (i < cur) cls = 'step-done';
    else if (i === cur) cls = 'step-active';
    return `<span class="${cls}">${l}</span>` + (i < 4 ? ' <span class="arrow">→</span> ' : '');
  }).join('');
}

// ══════════════════════════════════════════════════════
//  Tab 1: 1688 抓取
// ══════════════════════════════════════════════════════
async function doScrape() {
  const url = document.getElementById('url1688').value.trim();
  if (!url) { showS('scrapeStatus', 'error', '请先粘贴 1688 商品链接'); return; }
  const btn = document.getElementById('btnScrape'); btn.disabled = true;
  showS('scrapeStatus', 'info', '正在提交采集任务...');

  try {
    const res = await fetch(`${A8_API}/scraper/scrape`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({url}) });
    if (!res.ok) { const d = await res.json().catch(()=>({})); const detail = d.detail; const msg = typeof detail === 'string' ? detail : (Array.isArray(detail) ? detail.map(e=>e.msg).join('; ') : `HTTP ${res.status}`); throw new Error(msg); }
    const data = await res.json();
    const taskId = data.data.task_id;
    showS('scrapeStatus', 'info', '正在打开 1688 页面采集图片（约 10-20 秒）...');

    // 轮询容错：网络抖动继续重试，累计约 3 分钟无结果才超时
    let attempts = 0;
    const poll = setInterval(async () => {
      try {
        const r = await fetch(`${A8_API}/tasks/${taskId}`);
        const j = await r.json();
        const d = j.data;
        if (!d) return;
        if (d.status === 'SUCCESS') {
          clearInterval(poll);
          S.scrapedTaskId = taskId;
          S.scrapedFolder = d.result.folder;
          // 缓存采集图片 URL 供图库侧边栏使用
          const imgs = d.result.images;
          if (imgs) {
            ['main_images','sku_images','detail_images'].forEach(cat => {
              (imgs[cat] || []).forEach(img => {
                if (img.url) S._genImages.push({ url: img.url, type: img.filename || '', position: '', source: cat });
              });
            });
          }
          renderImageBank();
          showS('scrapeStatus', 'success', `采集完成 · ${d.result.image_count} 张图片`);
          btn.disabled = false;
        } else if (d.status === 'FAILURE') {
          clearInterval(poll);
          showS('scrapeStatus', 'error', `采集失败: ${typeof d.error_message === 'string' ? d.error_message : '未知错误'}`);
          btn.disabled = false;
        } else if (++attempts > 120) {
          clearInterval(poll);
          showS('scrapeStatus', 'error', '采集超时，请重试');
          btn.disabled = false;
        }
      } catch (e) { /* 网络抖动：下轮继续重试 */ }
    }, 1500);
  } catch(e) { showS('scrapeStatus', 'error', `采集失败: ${e.message}`); btn.disabled = false; }
}

// ══════════════════════════════════════════════════════
//  Tab 2: 产品分析 (port 8000)
// ══════════════════════════════════════════════════════

// 文件上传
function renderAnaPreviews(files) {
  S.productImageFiles = Array.from(files);
  const grid = document.getElementById('anaPreviews');
  grid.innerHTML = '';
  S.productImageFiles.forEach((f, i) => {
    const r = new FileReader();
    r.onload = e => {
      const wrap = document.createElement('div'); wrap.className = 'img-wrap sel';
      const img = document.createElement('img'); img.src = e.target.result; img.loading = 'lazy';
      const chk = document.createElement('div'); chk.className = 'chk'; chk.textContent = '✓';
      wrap.appendChild(img); wrap.appendChild(chk);
      wrap.addEventListener('click', () => { S.productImageFiles.splice(i, 1); renderAnaPreviews(S.productImageFiles); });
      grid.appendChild(wrap);
    };
    r.readAsDataURL(f);
  });
}
document.getElementById('anaFile').addEventListener('change', function() {
  if (this.files.length) renderAnaPreviews(this.files);
});
document.getElementById('anaUploadZone').addEventListener('dragover', e => { e.preventDefault(); });
document.getElementById('anaUploadZone').addEventListener('drop', e => {
  e.preventDefault();
  const dt = new DataTransfer();
  Array.from(e.dataTransfer.files).forEach(f => dt.items.add(f));
  document.getElementById('anaFile').files = dt.files;
  if (e.dataTransfer.files.length) renderAnaPreviews(e.dataTransfer.files);
});

async function doAnalyze() {
  const name = document.getElementById('anaName').value.trim();
  const func = document.getElementById('anaFunc').value.trim();
  const price = document.getElementById('anaPrice').value.trim();
  const extra = document.getElementById('anaExtra').value.trim();
  if (!name || !func || !price) { showS('anaStatus', 'error', '请先填写产品标题、功能和SKU规格'); return; }
  if (!S.productImageFiles.length) { showS('anaStatus', 'error', '请先上传至少一张产品图片'); return; }

  // 回存共享状态
  S.productTitle = name;
  S.productPoints = func;

  document.getElementById('btnAnalyze').disabled = true;
  showS('anaStatus', 'info', `已选 ${S.productImageFiles.length} 张图片，提交分析任务...`);

  try {
    const fd = new FormData();
    fd.append('name', name); fd.append('function', func); fd.append('price', price);
    fd.append('extra', extra);
    fd.append('custom_prompt', document.getElementById('anaSystemPrompt').value);
    fd.append('model', document.getElementById('anaModel').value);
    S.productImageFiles.forEach(f => fd.append('images', f));
    const res = await fetch(`${A8_API}/analysis/submit`, { method:'POST', body: fd });
    if (!res.ok) { const d = await res.json().catch(()=>({})); throw new Error(d.message || d.detail || `HTTP ${res.status}`); }
    const payload = await res.json();
    const taskId = payload?.data?.task_id;
    if (!taskId) throw new Error('未返回 task_id');
    showS('anaStatus', 'info', `分析中（约30-60秒）... 任务ID: ${taskId}`);
    S.anaTaskId = taskId;
    poll8000(taskId, (result) => {
      document.getElementById('btnAnalyze').disabled = false;
      if (!result.analysis) { showS('anaStatus', 'error', '分析报告为空'); return; }
      S.anaReport = result.analysis;
      showS('anaStatus', 'success', '分析完成');
      renderAnaReport(result.analysis, taskId);
    }, (err) => {
      document.getElementById('btnAnalyze').disabled = false;
      showS('anaStatus', 'error', `分析失败: ${err}`);
    });
  } catch(e) {
    document.getElementById('btnAnalyze').disabled = false;
    showS('anaStatus', 'error', `请求失败: ${e.message}`);
  }
}

function renderAnaReport(md, taskId) {
  const html = marked.parse(md);
  document.getElementById('anaReport').innerHTML = `
    <div class="report-card">
      <h2>📋 产品深度分析报告</h2>
      <div class="markdown-body">${html}</div>
      <div style="font-size:11px;color:var(--text2);margin-top:12px;text-align:right;">🆔 ${taskId}</div>
    </div>`;
}

// ── 差异化策略生成 ──

async function doDiffStrategies() {
  const report = document.getElementById('dsReport').value.trim();
  if (!report) { showS('dsStatus', 'error', '请先粘贴或导入分析报告'); return; }

  document.getElementById('btnDiffStrategy').disabled = true;
  showS('dsStatus', 'info', '策略生成中（约10-20秒）...');

  try {
    const body = JSON.stringify({
      analysis: report,
      system_prompt: document.getElementById('dsSystemPrompt').value,
      model: document.getElementById('dsModel').value,
    });
    const res = await fetch(`${A8_API}/analysis/strategies`, {
      method:'POST',
      headers: {'Content-Type': 'application/json'},
      body,
    });
    if (!res.ok) { const d = await res.json().catch(()=>({})); throw new Error(d.message || d.detail || `HTTP ${res.status}`); }
    const payload = await res.json();
    const taskId = payload?.data?.task_id;
    if (!taskId) throw new Error('未返回 task_id');
    showS('dsStatus', 'info', `生成中... 任务ID: ${taskId}`);
    poll8000(taskId, (result) => {
      document.getElementById('btnDiffStrategy').disabled = false;
      if (!result.strategies) { showS('dsStatus', 'error', '策略数据为空'); return; }
      S.anaStrategies = result.strategies;
      showS('dsStatus', 'success', '策略生成完成');
      document.getElementById('dsResults').innerHTML = '<div id="stratResult_"></div>';
      try {
        renderStrategiesTo(result.strategies, 'stratResult_');
      } catch(re) {
        console.error('renderStrategiesTo error:', re);
        showS('dsStatus', 'error', `渲染失败: ${re.message}`);
        document.getElementById('dsResults').innerHTML = `<pre style="background:#1a1a2e;color:#f44;padding:16px;overflow:auto;max-height:400px;font-size:12px;">${re.stack||re.message}</pre>`;
      }
    }, (err) => {
      document.getElementById('btnDiffStrategy').disabled = false;
      showS('dsStatus', 'error', `生成失败: ${err}`);
    });
  } catch(e) {
    document.getElementById('btnDiffStrategy').disabled = false;
    showS('dsStatus', 'error', `请求失败: ${e.message}`);
  }
}

function importAnalysisReport() {
  if (!S.anaReport) { showS('dsStatus', 'error', '请先在「深度分析」Tab 完成产品分析'); return; }
  document.getElementById('dsReport').value = S.anaReport;
  showS('dsStatus', 'success', '已导入深度分析报告');
}

function renderStrategiesTo(strategies, containerId) {
  const keys = ['A','B','C'];
  const styles = { A:{cls:'a',title:'方案A · 痛点解决型',color:'#0f0f0f'},
                   B:{cls:'b',title:'方案B · 效率功能型',color:'#0f0f0f'},
                   C:{cls:'c',title:'方案C · 情绪品质型',color:'#0f0f0f'} };
  let html = '<div class="strategy-grid">';
  keys.forEach(k => {
    const s = strategies[k]; if (!s) return;
    const st = styles[k];
    const pos = s.positioning || {};
    const comp = s.competitor_guess || {};
    const kw = s.keywords || {};
    const price = s.pricing || {};
    const rev = s.review_strategy || {};
    html += `<div class="strategy-card">
      <div class="strategy-header ${st.cls}">${s.route_name || st.title}</div>
      <div class="strategy-body">
        <div class="ref-upload-section">
          <span class="ref-label">📎 参考图</span>
          <label class="ref-upload-btn" for="refUpload_${k}">+ 上传</label>
          <input type="file" id="refUpload_${k}" accept="image/*" multiple style="display:none" onchange="handleRefUpload('${k}', this.files)">
          <span class="ref-label" style="font-size:10px;">可选，作为AI生图风格参考</span>
          <div class="ref-preview-list" id="refPreview_${k}"></div>
        </div>
        <details class="strategy-section" open>
          <summary>🎯 定位分析</summary>
          <div class="sec-content">
            <p><strong>目标用户</strong></p>
            <div class="strategy-tags">${(pos.target_users||[]).map(u=>`<span class="tag tag-blue">${esc(u)}</span>`).join('')}</div>
            <p style="margin-top:6px;"><strong>核心痛点</strong></p>
            <div class="strategy-tags">${(pos.core_pain_points||[]).map(p=>`<span class="tag tag-orange">${esc(p)}</span>`).join('')}</div>
            <p style="margin-top:8px;"><strong>差异化锚点</strong><br>${esc(pos.anchor_point||'—')}</p>
          </div>
        </details>
        <details class="strategy-section">
          <summary>🔍 竞品推测</summary>
          <div class="sec-content">
            <table class="sec-table"><tr><td>价格区间</td><td>${esc(comp.price_range||'—')}</td></tr><tr><td>竞品风格</td><td>${esc(comp.style_summary||'—')}</td></tr><tr><td>市场机会</td><td>${esc(comp.gap_opportunity||'—')}</td></tr></table>
          </div>
        </details>
        <details class="strategy-section">
          <summary>🔑 标题与关键词</summary>
          <div class="sec-content">
            <p><strong>建议标题</strong><br><span style="background:var(--bg);padding:3px 8px;border-radius:4px;">${esc(kw.title_suggestion||'—')}</span></p>
            <p style="margin-top:6px;"><strong>核心大词</strong></p>
            <div class="strategy-tags">${(kw.core_keywords||[]).map(w=>`<span class="tag tag-blue">${esc(w)}</span>`).join('')}</div>
            <p style="margin-top:4px;"><strong>场景长尾词</strong></p>
            <div class="strategy-tags">${(kw.scene_keywords||[]).map(w=>`<span class="tag tag-green">${esc(w)}</span>`).join('')}</div>
            <p style="margin-top:4px;"><strong>功能长尾词</strong></p>
            <div class="strategy-tags">${(kw.feature_keywords||[]).map(w=>`<span class="tag tag-orange">${esc(w)}</span>`).join('')}</div>
          </div>
        </details>
        <details class="strategy-section">
          <summary>🖼️ 主图方案（5张）<span style="font-weight:400;font-size:11px;color:var(--text3);margin-left:auto;" id="miCount_${k}"></span></summary>
          <div class="sec-content">
            <label class="select-all-row" onclick="toggleSelectAll('${k}','mi',event)"><input type="checkbox" id="miAll_${k}" onchange="toggleSelectAll('${k}','mi')"><span>全选 / 取消</span></label>
            ${(s.main_images||[]).map(m=>`<label class="img-check-row"><input type="checkbox" class="mi-cb-${k}" onchange="updateGenBtn('${k}')"><div class="img-check-body"><div class="main-img-item" style="border:none;padding:0;"><span class="mi-pos">${m.position}</span><span class="mi-title">${esc(m.type||'')}</span><span style="font-size:11px;color:var(--text3);margin-left:4px;">— ${esc(m.purpose||'')}</span><div style="font-size:11px;color:var(--text);margin-top:2px;"><strong>文案：</strong>${esc(m.title_text||'')}</div><div class="mi-prompt" title="${esc(m.prompt||'').replace(/"/g,'&quot;')}">${esc(m.prompt||'')}</div></div></div></label>`).join('')}
          </div>
        </details>
        <details class="strategy-section">
          <summary>📄 详情页规划（5屏）<span style="font-weight:400;font-size:11px;color:var(--text3);margin-left:auto;" id="dpCount_${k}"></span></summary>
          <div class="sec-content">
            <label class="select-all-row" onclick="toggleSelectAll('${k}','dp',event)"><input type="checkbox" id="dpAll_${k}" onchange="toggleSelectAll('${k}','dp')"><span>全选 / 取消</span></label>
            ${(s.detail_pages||[]).map(d=>`<label class="img-check-row"><input type="checkbox" class="dp-cb-${k}" onchange="updateGenBtn('${k}')"><div class="img-check-body"><div class="detail-item" style="border:none;padding:0;"><span class="di-pos">${d.position}</span><span class="mi-title">${esc(d.type||'')}</span><span style="font-size:11px;color:var(--text3);margin-left:4px;">— ${esc(d.purpose||'')}</span><div style="font-size:11px;color:var(--text);margin-top:2px;"><strong>标题：</strong>${esc(d.section_title||'')}</div><div class="mi-prompt" title="${esc(d.prompt||'').replace(/"/g,'&quot;')}">${esc(d.prompt||'')}</div></div></div></label>`).join('')}
          </div>
        </details>
        <details class="strategy-section">
          <summary>💰 定价与SKU</summary>
          <div class="sec-content">
            <p><strong>建议售价</strong> ${esc(price.suggested_price_range||'—')}</p>
            <table class="sec-table" style="margin-top:6px;"><tr><td style="width:50px;">类型</td><td>规格</td><td style="width:80px;">目的</td></tr>${(price.sku_strategy||[]).map(sku=>`<tr><td>${esc(sku.name||'')}</td><td>${esc(sku.desc||'')}</td><td>${esc(sku.purpose||'')}</td></tr>`).join('')}</table>
            <p style="margin-top:6px;"><strong>锚点说明</strong> ${esc(price.anchor_note||'—')}</p>
          </div>
        </details>
        <details class="strategy-section">
          <summary>⭐ 评价破零</summary>
          <div class="sec-content">
            <p><strong>引导关键词</strong></p>
            <div class="strategy-tags">${(rev.guided_keywords||[]).map(w=>`<span class="tag tag-blue">${esc(w)}</span>`).join('')}</div>
            <p style="margin-top:6px;"><strong>买家秀建议</strong></p><ul>${(rev.photo_suggestions||[]).map(p=>`<li>${esc(p)}</li>`).join('')}</ul>
            <p style="margin-top:4px;"><strong>问大家埋词</strong></p><ul>${(rev.qa_seeds||[]).map(q=>`<li>${esc(q)}</li>`).join('')}</ul>
          </div>
        </details>
      </div>
      <div class="strategy-actions">
        <select id="genSize_${k}" style="height:32px;padding:4px 8px;border:1px solid var(--border);border-radius:4px;font-size:12px;background:var(--bg);margin-right:6px;">
          <option value="2048x2048">2048×2048</option>
          <option value="2560x1440">2560×1440</option>
          <option value="1440x2560">1440×2560</option>
          <option value="1920x1920">1920×1920</option>
        </select>
        <button class="btn btn-ghost btn-sm" id="btnGenImg_${k}" onclick="genSelectedImages('${k}')" disabled>🎨 生成选中图</button>
        <button class="btn btn-ghost btn-sm" onclick="strategyToVideo('${k}')">🎬 做视频</button>
      </div>
      <div id="stratImg_${k}" style="padding:0 16px 14px;"></div>
    </div>`;
  });
  html += '</div>';
  document.getElementById(containerId).innerHTML = html;
}

// ── 参考图存储（每个策略 key 对应一组 File）
const _refImages = {};

function handleRefUpload(key, fileList) {
  if (!fileList || !fileList.length) return;
  if (!_refImages[key]) _refImages[key] = [];
  const preview = document.getElementById('refPreview_'+key);
  for (const f of fileList) {
    const idx = _refImages[key].length;
    _refImages[key].push(f);
    const url = URL.createObjectURL(f);
    const wrap = document.createElement('div'); wrap.className = 'ref-preview-item';
    const img = document.createElement('img'); img.src = url; img.title = f.name;
    img.onclick = () => window.open(url);
    const del = document.createElement('span'); del.className = 'ref-del-btn'; del.textContent = '×';
    del.onclick = (e) => { e.stopPropagation(); removeRefImage(key, idx); };
    wrap.appendChild(img); wrap.appendChild(del);
    preview.appendChild(wrap);
  }
  document.getElementById('refUpload_'+key).value = '';
}

function removeRefImage(key, idx) {
  if (!_refImages[key]) return;
  _refImages[key].splice(idx, 1);
  const preview = document.getElementById('refPreview_'+key);
  if (preview) {
    // 重新构建预览（因为 index 变了）
    preview.innerHTML = '';
    _refImages[key].forEach((f, i) => {
      const url = URL.createObjectURL(f);
      const wrap = document.createElement('div'); wrap.className = 'ref-preview-item';
      const img = document.createElement('img'); img.src = url; img.title = f.name;
      img.onclick = () => window.open(url);
      const del = document.createElement('span'); del.className = 'ref-del-btn'; del.textContent = '×';
      del.onclick = (e) => { e.stopPropagation(); removeRefImage(key, i); };
      wrap.appendChild(img); wrap.appendChild(del);
      preview.appendChild(wrap);
    });
  }
}

function toggleSelectAll(key, type, event) {
  if (event && event.target.tagName === 'INPUT') return;
  const cls = type === 'mi' ? 'mi-cb-' + key : 'dp-cb-' + key;
  const allId = type === 'mi' ? 'miAll_' + key : 'dpAll_' + key;
  const allCb = document.getElementById(allId);
  const cbs = document.querySelectorAll('.' + cls);
  const allChecked = Array.from(cbs).every(cb => cb.checked);
  const newState = !allChecked;
  cbs.forEach(cb => { cb.checked = newState; });
  if (allCb) allCb.checked = newState;
  updateGenBtn(key);
}

function updateGenBtn(key) {
  const miCbs = document.querySelectorAll('.mi-cb-' + key);
  const dpCbs = document.querySelectorAll('.dp-cb-' + key);
  const miChecked = Array.from(miCbs).filter(cb => cb.checked).length;
  const dpChecked = Array.from(dpCbs).filter(cb => cb.checked).length;
  const total = miChecked + dpChecked;
  const btn = document.getElementById('btnGenImg_' + key);
  if (btn) {
    btn.disabled = total === 0;
    btn.textContent = total > 0 ? `🎨 生成选中图 (${total})` : '🎨 生成选中图';
  }
  const miAll = document.getElementById('miAll_' + key);
  if (miAll) miAll.checked = miCbs.length > 0 && miChecked === miCbs.length;
  const dpAll = document.getElementById('dpAll_' + key);
  if (dpAll) dpAll.checked = dpCbs.length > 0 && dpChecked === dpCbs.length;
}

async function genSelectedImages(key) {
  const s = S.anaStrategies[key]; if (!s) return;
  const container = document.getElementById('stratImg_'+key);

  const miCbs = document.querySelectorAll('.mi-cb-' + key);
  const selectedMI = [];
  miCbs.forEach((cb, i) => { if (cb.checked && s.main_images && s.main_images[i]) selectedMI.push(s.main_images[i]); });

  const dpCbs = document.querySelectorAll('.dp-cb-' + key);
  const selectedDP = [];
  dpCbs.forEach((cb, i) => { if (cb.checked && s.detail_pages && s.detail_pages[i]) selectedDP.push(s.detail_pages[i]); });

  const total = selectedMI.length + selectedDP.length;
  if (!total) { showS('dsStatus', 'error', '请先至少勾选一张图'); return; }

  container.innerHTML = `<div style="font-size:13px;color:var(--accent);padding:8px;">正在生成 ${total} 张图...</div>`;

  try {
    const fd = new FormData();
   if (_refImages[key] && _refImages[key].length) {
     _refImages[key].forEach(f => fd.append('ref_images', f));
   }
    // 自动用深度分析上传的产品原图作为生图参考
    if (!_refImages[key] || !_refImages[key].length) {
      const af = document.getElementById('anaFile');
      if (af && af.files && af.files.length) {
        Array.from(af.files).forEach(f => fd.append('ref_images', f));
      }
    }
    const tagged = [
      ...selectedMI.map(s => ({...s, source: 'main'})),
      ...selectedDP.map(s => ({...s, source: 'detail'}))
    ];
    fd.append('prompts', JSON.stringify(tagged));
    const sizeEl = document.getElementById('genSize_' + key);
    if (sizeEl && sizeEl.value) fd.append('size', sizeEl.value);
    const modelEl = document.getElementById('dsGenModel');
    if (modelEl && modelEl.value) fd.append('model', modelEl.value);

    const res = await fetch(`${A8_API}/images/generate`, { method:'POST', body:fd });
    if (!res.ok) throw new Error((await res.json().catch(()=>({})).message || `HTTP ${res.status}`));
    const payload = await res.json();
    const taskId = payload?.data?.task_id;
    poll8000(taskId, (result) => {
      const imgs = result.images || [];
      // 缓存 URL 供图库侧边栏使用
      imgs.forEach(img => {
        const src = img.remote_url || img.local_path;
        if (src) S._genImages.push({ url: src, type: img.type || '', position: img.position, source: img.source || '' });
      });
      renderImageBank();
      const successImgs = imgs.filter(i => i.remote_url || i.local_path);
      const failImgs = imgs.filter(i => !i.remote_url && !i.local_path);
      let imgHtml = '<div style="margin-top:8px;">';
      if (successImgs.length) {
        imgHtml += `<div style="font-size:11px;color:var(--green);margin-bottom:4px;">✅ 成功 ${successImgs.length} 张</div>`;
        imgHtml += '<div style="display:flex;gap:6px;flex-wrap:wrap;">';
        successImgs.forEach(img => {
          const src = img.remote_url || img.local_path;
          const label = `${img.type || ''} #${img.position}`;
          const fname = `${img.source||'img'}_pos${img.position}_${img.type||''}.png`.replace(/\s+/g,'_');
          imgHtml += `<div style="text-align:center;max-width:90px;"><img src="${esc(src)}" style="width:72px;height:72px;border-radius:10px;object-fit:cover;cursor:pointer;border:1px solid var(--border);" onclick="openLightbox('${esc(src)}','${esc(fname)}')" onerror="this.style.display='none'" title="点击放大\n文件: ${esc(fname)}"><div style="font-size:10px;color:var(--text2);word-break:break-all;margin-top:2px;max-width:80px;">${esc(label)}</div></div>`;
        });
        imgHtml += '</div>';
      }
      if (failImgs.length) {
        imgHtml += `<div style="font-size:11px;color:var(--red);margin-top:4px;">❌ 失败 ${failImgs.length} 张: ${failImgs.map(i=>esc(i.error||'未知')).join(', ')}</div>`;
      }
      if (result.output_dir) {
        imgHtml += `<div style="font-size:10px;color:var(--text3);margin-top:4px;">📁 保存至: ${esc(result.output_dir)}</div>`;
      }
      imgHtml += '</div>';
      container.innerHTML = imgHtml;
    }, (err) => { container.innerHTML = `<div style="font-size:12px;color:var(--red);">失败: ${err}</div>`; });
  } catch(e) { container.innerHTML = `<div style="font-size:12px;color:var(--red);">错误: ${e.message}</div>`; }
}

function strategyToVideo(key) {
  if (!S.anaStrategies) { showS('dsStatus', 'error', '请先生成策略方案'); return; }
  const s = S.anaStrategies[key];
  if (!s) { showS('dsStatus', 'error', `方案 ${key} 数据不存在，请先重新生成策略`); return; }

  const pos = s.positioning || {};
  const kw = s.keywords || {};

  // 钩子：首个痛点作为参考文案
  const painPoints = pos.core_pain_points || [];

  // ═══════ 构建自定义口播内容（从策略搬运所有文案相关信息） ═══════
  const lines = [];
  if (S.productTitle) lines.push(`产品：${S.productTitle}`);
  if (S.productPoints) lines.push(`功能/卖点：${S.productPoints}`);
  if (lines.length) lines.push('');
  // 目标人群
  const users = pos.target_users || [];
  if (users.length) lines.push(`目标人群：${users.join('、')}`);
  // 核心卖点
  if (pos.anchor_point) lines.push(`差异化锚点：${pos.anchor_point}`);
  // 核心痛点
  if (painPoints.length) lines.push(`核心痛点：\n  · ${painPoints.join('\n  · ')}`);
  if (painPoints.length) lines.push('');
  // 策略类型
  const strategyNames = { A: '痛点解决型策略', B: '功能对比型策略', C: '场景代入型策略' };
  if (strategyNames[key]) lines.push(`策略类型：${strategyNames[key]}`);
  // 核心关键词
  const cats = kw.core_keywords || [];
  if (cats.length) lines.push(`核心关键词：${cats.join('、')}`);
  // 长尾关键词（可选）
  const longtail = kw.long_tail_keywords || [];
  if (longtail.length) lines.push(`长尾关键词：${longtail.join('、')}`);
  // 标题建议
  if (kw.title_suggestion) lines.push(`标题建议：${kw.title_suggestion}`);

  document.getElementById('vidCustomContent').value = lines.join('\n');

  switchTab('tabVideo');
  document.getElementById('tabVideo').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// Port 8000 轮询
function poll8000(taskId, onSuccess, onError) {
  let attempts = 0, max = 210, done = false;
  const poll = () => {
    if (done) return;
    attempts++;
    fetch(`${A8_API}/tasks/${taskId}`).then(r => r.json()).then(payload => {
      const d = payload?.data;
      if (!d) throw new Error('Invalid response');
      if (d.status === 'SUCCESS') { done = true; onSuccess(d.result); return; }
      if (d.status === 'FAILURE') { done = true; onError(d.error_message || '任务失败'); return; }
      if (attempts < max) setTimeout(poll, 2000); else onError('任务超时');
    }).catch(e => { if (attempts < max && !done) setTimeout(poll, 2000); else onError(`轮询失败: ${e.message}`); });
  };
  poll();
}

// 带进度的轮询：onProgress(pct, stage) 每次状态检查调用，onSuccess(result) 成功时调用
function pollWithProgress(taskId, onProgress, onSuccess, onError) {
  let attempts = 0, max = 450, done = false;
  const poll = () => {
    if (done) return;
    attempts++;
    fetch(`${A8_API}/tasks/${taskId}`).then(r => r.json()).then(payload => {
      const d = payload?.data;
      if (!d) throw new Error('Invalid response');
      if (d.status === 'SUCCESS') { done = true; onSuccess(d.result); return; }
      if (d.status === 'FAILURE') { done = true; onError(d.error_message || '任务失败'); return; }
      // RUNNING 状态：检查进度信息
      if (d.result && d.result.progress !== undefined) {
        onProgress(d.result.progress, d.result.stage || '');
      }
      if (attempts < max) setTimeout(poll, 2000); else onError('任务超时');
    }).catch(e => { if (attempts < max && !done) setTimeout(poll, 2000); else onError(`轮询失败: ${e.message}`); });
  };
  poll();
}

// 脚本生成（纯透传，不拆字段）
async function doGenScript() {
  const content = document.getElementById('vidCustomContent').value.trim();

  if (!content) { showS('vidScriptStatus', 'error', '请先在口播内容框输入内容'); return; }

  const btn = document.getElementById('btnGenScript');
  btn.disabled = true; btn.textContent = '⏳ 生成中...';
  showS('vidScriptStatus', 'info', 'AI 正在撰写口播脚本...');

  try {
    const res = await fetch(`${A8_API}/video/generate-script`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        content,
        segments: parseInt(document.getElementById('vidSegments').value) || 8,
        system_prompt: document.getElementById('vidSystemPrompt').value,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(apiErrMsg(err));
    }
    const data = await res.json();
    const taskId = data.data.task_id;
    S.scriptTaskId = taskId;
    poll8000(taskId, (result) => {
      S.scriptPath = result.script_path;
      S.vidScriptSegments = result.script.segments;
      document.getElementById('vidScript').value = result.script.segments.map((s, i) => {
        return `[镜${i + 1} ${s.type}]\n📢 ${s.voiceover}`;
      }).join('\n\n');
      // 自动填充配音文本：提取所有口播片段合并为纯文本
      document.getElementById('vidTtsText').value = result.script.segments.map(s => s.voiceover).join('\n');
      showS('vidScriptStatus', 'success', `已填充 · ${result.script.total_words} 字 · ${result.script.segments.length} 段`);
      btn.disabled = false; btn.textContent = '🤖 AI生成';
    }, (error) => {
      showS('vidScriptStatus', 'error', `生成失败: ${error}`);
      btn.disabled = false; btn.textContent = '🤖 AI生成';
    });
  } catch(e) { showS('vidScriptStatus', 'error', `提交失败: ${e.message}`); btn.disabled = false; btn.textContent = '🤖 AI生成'; }
}

// TTS
async function doGenTTS() {
  const text = document.getElementById('vidTtsText').value.trim();
  if (!text) { showS('vidTTSStatus', 'error', '请先填写配音文本'); return; }
  const btn = document.getElementById('btnGenTTS');
  btn.disabled = true; btn.textContent = '⏳ 配音中...';
  showS('vidTTSStatus', 'info', '');
  S._pendingShots = null;
  document.getElementById('vidTtsShotsCount').textContent = '配音完成后可导入镜头';

  try {
    const res = await fetch(`${A8_API}/video/generate-tts`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        text: text,
        voice: document.getElementById('vidVoice').value,
        rate: document.getElementById('vidRate').value,
        parent_task_id: S.scriptTaskId || null,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(apiErrMsg(err));
    }
    const data = await res.json();
    const pollTaskId = data.data.task_id;
    S.ttsTaskId = pollTaskId;
    poll8000(pollTaskId, (result) => {
      S.audioPath = result.audio_path; S.srtPath = result.srt_path;
      const audioEl = document.getElementById('vidTtsAudio');
      audioEl.src = result.audio_path;
      document.getElementById('vidAudioResult').style.display = '';
      document.getElementById('vidAudioDownload').href = result.audio_path;
      document.getElementById('vidAudioDownload').download = result.audio_path.split('/').pop() || 'audio.mp3';
      document.getElementById('vidSrtDownload').href = result.srt_path;
      document.getElementById('vidSrtDownload').download = result.srt_path.split('/').pop() || 'subtitle.srt';

      const shots = result.grouped_shots || [];

      if (shots.length) {
        S._pendingShots = shots;
        document.getElementById('vidTtsShotsCount').textContent = `${shots.length} 个镜头就绪`;
        showS('vidTTSStatus', 'success', `配音完成 · ${result.duration_sec.toFixed(1)}秒 · ${shots.length} 镜`);
      } else {
        showS('vidTTSStatus', 'success', `配音完成 · 时长 ${result.duration_sec.toFixed(1)} 秒`);
      }
      btn.disabled = false; btn.textContent = '🎙️ 重新配音';
    }, (error) => {
      showS('vidTTSStatus', 'error', `配音失败: ${error}`);
      btn.disabled = false; btn.textContent = '🎙️ AI 生成配音 + 字幕';
    });
  } catch(e) { showS('vidTTSStatus', 'error', `提交失败: ${e.message}`); btn.disabled = false; btn.textContent = '🎙️ AI 生成配音 + 字幕'; }
}

// 视频 AI 模型切换：Mini 不支持 1080p，禁用该选项并自动降到 720p
function vidAIModelChange() {
  const model = document.getElementById('vidAIModel').value;
  const isMini = model.includes('mini');
  const opt1080 = document.getElementById('vidRes1080p');
  if (opt1080) opt1080.disabled = isMini;
  const res = document.getElementById('vidResolution');
  if (isMini && res && res.value === '1080p') res.value = '720p';
}

// 合成参数渲染
// ── 上传素材区统一显隐（按模式 + 已上传数据计算，避免切换残留混乱）──
function syncUploadZones() {
  const mode = S.vidComposeMode || 'fast';
  const uploadSec = document.getElementById('vidUploadSection');
  const ttsImportBtn = document.getElementById('vidImportTtsBtn');
  if (!uploadSec) return;
  // 有声模式：Seedance 原生音频，外部素材整块隐藏
  // 无声·导入锁定态：素材已由配音定死（音频/字幕=配音产物），隐藏上传区防误传串味；DIY 态恢复显示
  const lockedSilent = mode === 'premium' && !S._diyMode && !!S._sbTtsTaskId;
  const showUpload = mode !== 'premium_audio' && !lockedSilent;
  uploadSec.style.display = showUpload ? '' : 'none';
  // 「从配音导入音频字幕」仅快速模式需要（精铺无声自动走配音链路）
  if (ttsImportBtn) ttsImportBtn.style.display = (mode === 'fast') ? '' : 'none';
  if (!showUpload) return;
  // 图片素材列仅快速模式
  const imgZone = document.getElementById('vidUploadImagesZone');
  const imgPreview = document.getElementById('vidUploadImagesPreview');
  if (imgZone) imgZone.style.display = (mode === 'fast') ? '' : 'none';
  if (imgPreview) imgPreview.style.display = (mode === 'fast') ? '' : 'none';
  // 音频/字幕列：快速/无声均显示，区内 zone↔卡片按数据互斥
  const audioCol = document.getElementById('vidAudioZone');
  const srtCol = document.getElementById('vidSrtZone');
  if (audioCol) audioCol.parentElement.style.display = '';
  if (srtCol) srtCol.parentElement.style.display = '';
  syncAudioCard();
  syncSrtCard();
}

// 音频列：有已上传音频则显示替换卡片，否则显示上传框
function syncAudioCard() {
  const zone = document.getElementById('vidAudioZone');
  const card = document.getElementById('vidUploadAudioCard');
  if (!zone || !card) return;
  zone.style.display = S.uploadedAudio ? 'none' : '';
  card.style.display = S.uploadedAudio ? '' : 'none';
}

// 字幕列：有已上传字幕则显示替换卡片，否则显示上传框
function syncSrtCard() {
  const zone = document.getElementById('vidSrtZone');
  const card = document.getElementById('vidUploadSrtCard');
  if (!zone || !card) return;
  zone.style.display = S.uploadedSrt ? 'none' : '';
  card.style.display = S.uploadedSrt ? '' : 'none';
}

function vidRenderComposeParams() {
  const mode = document.getElementById('vidCompose').value;
  const el = document.getElementById('vidComposeParams');
  const aiModelRow = document.getElementById('vidAIModelRow');
  const qualitySel = document.getElementById('vidQuality');
  if (mode === 'fast') {
    S.vidGenAudio = false;
    S.vidComposeMode = 'fast';
    qualitySel.disabled = false;  // 快速模式质量检查可选
    if (aiModelRow) aiModelRow.style.display = 'none';  // 快速模式不用 AI，隐藏模型选择
    el.innerHTML = `
      <div class="vid-lbl">转场风格</div>
      <select id="vidTransition" style="width:100%;height:38px;padding:6px 10px;border:1.5px solid var(--border);border-radius:var(--radius-sm);font-size:13px;background:var(--bg);">
        <option value="fade">淡入淡出</option>
        <option value="slide">滑动切换</option>
        <option value="zoom">缩放切换</option>
        <option value="random">随机混合</option>
      </select>`;
    document.getElementById('btnCompose').onclick = doCompose;
  } else {
    // 精品模式（有声/无声），状态隔离：切换时先保存当前 storyboard
    const prevMode = S.vidComposeMode || '';
    if (prevMode === 'premium' || prevMode === 'premium_audio') {
      // 保存当前模式的分镜（含 DIY 状态）
      S._sbCache = S._sbCache || {};
      S._sbCache[prevMode] = { storyboard: JSON.parse(JSON.stringify(S.storyboard)), diy: !!S._diyMode };
    }
    S.vidGenAudio = mode === 'premium_audio';
    S.vidComposeMode = mode;
    qualitySel.value = 'true';  // 精铺模式强制开启质量检查
    qualitySel.disabled = true;
    if (aiModelRow) aiModelRow.style.display = '';  // 精品模式显示模型选择
    el.innerHTML = '';
    // 恢复该模式之前保存的分镜，否则重新初始化
    if (S._sbCache && S._sbCache[mode]) {
      S.storyboard = JSON.parse(JSON.stringify(S._sbCache[mode].storyboard));
      S._diyMode = !!S._sbCache[mode].diy;
    } else {
      S._diyMode = false;
      initStoryboard();
    }
    renderStoryboard();
    document.getElementById('btnCompose').onclick = doComposePremium;
  }
  syncUploadZones();
}

// ══════════════════════════════════════════════════════
//  精铺模式：分镜编辑器
// ══════════════════════════════════════════════════════

// ── 场景描述：从口播脚本分镜数据中提取（AI 生成） ──

// 时长钳位到 API 支持的 [4,12] 范围
function snapDuration(v) {
  return Math.max(4, Math.min(12, Math.round(v)));
}

// ── 从口播脚本同步文案到分镜 ──
function initStoryboard() {
  if (!S.storyboard || !S.storyboard.shots || !S.storyboard.shots.length) {
    const segs = S.vidScriptSegments;
    const n = segs && segs.length ? segs.length : 3;
    const shots = [];
    for (let i = 0; i < n; i++) {
      const seg = segs && segs[i];
      shots.push({
        first_frame_url: '',
        last_frame_url: '',
        scene_prompt: '',
        voiceover: seg ? (seg.voiceover || '') : '',
        duration_sec: seg
          ? snapDuration(Math.max(4, Math.min(12, Math.round(seg.estimated_duration))))
          : 4,
      });
    }
    S.storyboard = { shots };
  }
}

function renderStoryboard() {
  const el = document.getElementById('vidComposeParams');
  // 首尾帧填写提示
  const imgSuggestionHtml = `<div style="margin:6px 0;padding:8px 10px;background:var(--bg);border:1px dashed var(--border);border-radius:6px;font-size:12px;color:var(--text2);line-height:1.6;">
        💡 <b>首帧</b>：每个镜头贴同一张产品主图即可，AI 根据场景描述自动生成运镜动画<br>
        💡 <b>尾帧</b>：一般留空，仅在需要精确控制镜头结束画面时填写
      </div>`;

  let total = 0;
  const shotsHtml = S.storyboard.shots.map((s, i) => {
    total += (s.duration_sec >= 4 && s.duration_sec <= 12) ? s.duration_sec : 4;
    // 无声·已导入锁定：配音相关字段（台词/时长）只读；画面配置（场景/首尾帧）仍可填
    const locked = !S.vidGenAudio && !S._diyMode && !!S._sbTtsTaskId;
    const lockAttr = locked ? 'disabled ' : '';
    // 合并标识
    const isMerged = s.merged_count && s.merged_count > 1;
    const mergeBadge = isMerged
      ? `<span style="display:inline-block;margin-left:6px;padding:1px 6px;background:#fff3cd;color:#856404;border-radius:3px;font-size:11px;font-weight:600;">${s.merged_count} 段合并</span>`
      : '';

    const selHtml = `<div style="display:flex;gap:8px;flex-direction:column;">
        <div style="display:flex;align-items:center;gap:4px;">
          <span style="font-size:11px;color:var(--text2);white-space:nowrap;">首帧</span>
          <input class="shot-input" placeholder="贴入图片 URL" value="${esc(s.first_frame_url || '')}"
            onchange="S.storyboard.shots[${i}].first_frame_url=this.value" style="flex:1;">
        </div>
        <div style="display:flex;align-items:center;gap:4px;">
          <span style="font-size:11px;color:var(--text2);white-space:nowrap;">尾帧</span>
          <input class="shot-input" placeholder="选填，控制视频结束画面" value="${esc(s.last_frame_url || '')}"
            onchange="S.storyboard.shots[${i}].last_frame_url=this.value" style="flex:1;">
        </div>
      </div>`;

    return `<div class="shot-card" id="shotCard${i}" style="${isMerged ? 'border-color:#ffc107;border-width:2px;' : ''}">
      <div class="shot-header">
        <span class="shot-header-num">镜${i + 1}${mergeBadge}</span>
        ${lockAttr ? '' : `<button class="shot-header-del" onclick="removeShot(${i})" title="删除">×</button>`}
      </div>
      <div class="shot-body">
        <div class="shot-body-row">
          <div class="shot-field" style="flex:1">
            <span class="shot-lbl">场景描述</span>
            <textarea class="shot-input" placeholder="如：白色办公桌，自然光，MacBook旁边…" onchange="S.storyboard.shots[${i}].scene_prompt=this.value" style="resize:vertical;min-height:56px;">${esc(s.scene_prompt)}</textarea>
          </div>
        </div>
        <div class="shot-body-row">
          <div class="shot-field" style="flex:1">
            <span class="shot-lbl">口播台词</span>
            <textarea class="shot-input" ${lockAttr}placeholder="此镜头台词…" onchange="S.storyboard.shots[${i}].voiceover=this.value" style="resize:vertical;min-height:44px;font-size:12px;color:var(--text2);">${esc(s.voiceover || '')}</textarea>
          </div>
        </div>
        <div class="shot-body-row">
          <div class="shot-field">
            <span class="shot-lbl">参考图</span>
            ${selHtml}
          </div>
          <div class="shot-field">
            <span class="shot-lbl">展示时长</span>
            <div class="shot-dur-wrap" style="display:flex;align-items:center;gap:4px;">
              <select id="shotDur${i}" ${lockAttr}onchange="S.storyboard.shots[${i}].duration_sec=parseInt(this.value);renderStoryboardFooter()" style="width:60px;height:32px;font-size:12px;text-align:center;border:1px solid var(--border);border-radius:4px;padding:2px 4px;">
                ${[4,5,6,7,8,9,10,11,12].map(v => `<option value="${v}" ${Math.round(s.duration_sec)===v?'selected':''}>${v}s</option>`).join('')}
              </select>
            </div>
          </div>
        </div>
        ${s.clip_url ? `<div class="shot-body-row"><video class="shot-clip-preview" src="${s.clip_url}" controls muted style="width:100%;max-height:200px;border-radius:6px;"></video></div>` : ''}
        ${s.clip_status === 'error' && s.clip_error ? `<div class="shot-body-row" style="color:#e53e3e;font-size:11px;line-height:1.5;word-break:break-all;" title="${esc(s.clip_error)}">❌ ${esc(s.clip_error.slice(0, 200))}${s.clip_error.length > 200 ? '…' : ''}</div>` : ''}
        <div class="shot-body-row" style="display:flex;align-items:center;gap:8px;">
          <button class="btn btn-ghost btn-sm" onclick="generateShot(${i})" id="btnGenShot${i}" style="flex:1;${s.clip_status==='running'?'opacity:0.6':''}">
            ${s.clip_status === 'running' ? '⏳ 生成中...' : s.clip_url ? '🔄 重新生成' : '▶ 生成此镜'}
          </button>
        </div>
      </div>
    </div>`;
  }).join('');

  el.innerHTML = `
    <div class="storyboard-wrap">
      ${imgSuggestionHtml}
      <div class="storyboard-list" id="shotList">${shotsHtml}</div>
      ${(S.vidGenAudio || S._diyMode || !S._sbTtsTaskId) ? '<button class="btn-shot-add" onclick="addShot()">+ 添加分镜</button>' : ''}
      <div class="storyboard-footer" id="storyboardFooter">
        <span class="storyboard-total">共 ${S.storyboard.shots.length} 镜 · 总时长 ${total.toFixed(1)}s</span>
      </div>
    </div>`;
  // 同步顶部「清空镜头」按钮（有声/无声有镜头时都显示，点一下回到 3 空框初始状态）
  const clearBtn = document.getElementById('btnClearShots');
  if (clearBtn) clearBtn.style.display = S.storyboard.shots.length ? '' : 'none';
}

function renderStoryboardFooter() {
  const foot = document.getElementById('storyboardFooter');
  if (!foot) return;
  let total = 0;
  S.storyboard.shots.forEach(s => total += (s.duration_sec >= 4 && s.duration_sec <= 12) ? s.duration_sec : 4);
  foot.innerHTML = `<span class="storyboard-total">共 ${S.storyboard.shots.length} 镜 · 总时长 ${total.toFixed(1)}s</span>`;
}

function addShot() {
  S.storyboard.shots.push({ first_frame_url: '', last_frame_url: '', scene_prompt: '', voiceover: '', duration_sec: 5 });
  renderStoryboard();
}

// 清空镜头，重置为 3 个空镜头（无声锁定态点它即退出配音锁定，回到自由编辑）
function clearStoryboard() {
  if (!confirm('清空所有镜头并重置为 3 个空镜头？')) return;
  S.storyboard = { shots: [0, 1, 2].map(() => ({ first_frame_url: '', last_frame_url: '', scene_prompt: '', voiceover: '', duration_sec: 5 })) };
  S._diyMode = true;
  S._sbTtsTaskId = null;
  S.uploadedAudio = '';
  S.uploadedSrt = '';
  syncUploadZones();
  renderStoryboard();
  showToast('success', '已初始化镜头');
}

function removeShot(i) {
  if (S.storyboard.shots.length <= 1) return;
  S.storyboard.shots.splice(i, 1);
  renderStoryboard();
}

// ── 独立生成单个分镜 ──
async function generateShot(i) {
  const shot = S.storyboard.shots[i];
  if (shot.clip_status === 'running') return;

  // 拦截空内容：既无图也无场景描述
  const firstFrame = shot.first_frame_url || '';
  const hasImage = (firstFrame || shot.last_frame_url);
  const hasPrompt = (shot.scene_prompt || '').trim();
  if (!hasImage && !hasPrompt) {
    const btnEl = document.getElementById('btnGenShot' + i);
    if (btnEl) { btnEl.textContent = '⚠️ 请先填写场景描述或参考图'; btnEl.style.color = '#e53e3e'; }
    return;
  }

  shot.clip_status = 'running';
  renderStoryboard();

  const specRadio = document.querySelector('input[name="vidSpec"]:checked');
  const spec = specRadio ? specRadio.value : '9:16';
  const genAudio = document.getElementById('vidCompose').value === 'premium_audio';
  const resSelect = document.getElementById('vidResolution');
  const resolution = resSelect ? resSelect.value : '720p';

  const btnEl = document.getElementById('btnGenShot' + i);

  // 时长：优先从 DOM 读（用户真实输入），仅无效时才读状态
  const durInput = document.getElementById('shotDur' + i);
  let actualDur = shot.duration_sec;
  if (durInput) {
    const v = parseInt(durInput.value, 10);
    if (v >= 4 && v <= 12) actualDur = v;
  }

  try {
    const res = await fetch(`${A8_API}/video/generate-shot`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        first_frame_url: shot.first_frame_url || '',
        last_frame_url: shot.last_frame_url || '',
        scene_prompt: shot.scene_prompt_en || shot.scene_prompt || '',
        voiceover: shot.voiceover || '',
        duration_sec: actualDur,
        aspect_ratio: spec,
        generate_audio: genAudio,
        resolution: resolution,
        video_model: document.getElementById('vidAIModel') ? document.getElementById('vidAIModel').value : '',
        shot_index: i,
        parent_task_id: S.ttsTaskId || null,
      }),
    });

    if (!res.ok) {
      const txt = await res.text();
      throw new Error(apiErrMsg(txt));
    }

    const data = await res.json();
    const taskId = data.data.task_id;
    // 轮询进度
    let pollTimer = setInterval(async () => {
      try {
        const r = await fetch(`${A8_API}/tasks/${taskId}`);
        const p = await r.json();
        const d = p?.data;
        if (!d) return;
        if (d.status === 'RUNNING' && d.result) {
          if (btnEl) btnEl.textContent = '⏳ ' + (d.result.detail || d.result.stage || '处理中...');
        }
        if (d.status === 'SUCCESS') {
          clearInterval(pollTimer);
          shot.clip_url = d.result.video_path;
          shot.clip_audio = genAudio;  // 记录该素材是否为有声版
          shot.clip_status = 'done';
          renderStoryboard();
        }
        if (d.status === 'FAILURE') {
          clearInterval(pollTimer);
          shot.clip_status = 'error';
          shot.clip_error = d.error_message || (d.result && d.result.error) || '生成失败，请重试';
          renderStoryboard();
        }
      } catch (_) {}
    }, 2000);
  } catch (e) {
    shot.clip_status = 'error';
    shot.clip_error = e.message || '请求失败，请重试';
    renderStoryboard();
  }
}

// 精铺模式合成
async function doComposePremium() {
  const allShots = S.storyboard.shots;
  if (!allShots.length) { showS('vidComposeStatus', 'error', '请先在「配音设置」配音并导入镜头到分镜'); return; }

  // 强制全量：配音只做一次，所有镜头必须生成视频后才能合成
  const missing = [];
  allShots.forEach((s, i) => { if (!s.clip_url) missing.push(i + 1); });
  if (missing.length) {
    showS('vidComposeStatus', 'error', `请先生成第 ${missing.join('、')} 镜视频后再合成`);
    return;
  }

  // 有声模式：素材必须是有声版
  if (S.vidGenAudio) {
    const silentIdx = allShots.findIndex(s => !s.clip_audio);
    if (silentIdx > -1) {
      showS('vidComposeStatus', 'error', `第 ${silentIdx + 1} 镜视频无声音：请在该镜勾选“有声”重新生成，或关闭有声模式`);
      return;
    }
  }

  const hasUploadedAudio = S.uploadedAudio && S.uploadedAudio.length;
  const hasUploadedSrt = S.uploadedSrt && S.uploadedSrt.length;

  // 无声模式（非 DIY）：storyboard 必须与当前配音同批次（配音更新后需重新导入）
  if (!S.vidGenAudio && !S._diyMode && S.ttsTaskId !== S._sbTtsTaskId) {
    showS('vidComposeStatus', 'error', '分镜与配音不一致：请先点击「导入镜头到分镜」；若想自由拼装，请先「清空镜头」并上传自己的音频素材');
    return;
  }

  // 无声模式直接复用第一次配音产物（不重新配音）；DIY 模式用上传区音频
  const composeAudioPath = S.vidGenAudio || S._diyMode ? '' : (S.audioPath || '');
  const composeSrtPath = S.vidGenAudio || S._diyMode ? '' : (S.srtPath || '');
  if (!S.vidGenAudio && !S._diyMode && !hasUploadedAudio && !composeAudioPath) {
    showS('vidComposeStatus', 'error', '请先在「配音设置」生成配音');
    return;
  }
  const composeParentId = S.ttsTaskId || null;

  const btn = document.getElementById('btnCompose');
  btn.disabled = true; btn.textContent = '⏳ 合成中...';
  document.getElementById('vidComposeStatus').textContent = '';

  const wrap = document.getElementById('vidComposeProgress');
  const bar = document.getElementById('vidComposeBar');
  const stage = document.getElementById('vidComposeStage');
  wrap.style.display = ''; bar.style.width = '0%'; stage.textContent = '准备中...';

  try {
    const shotsWithClips = allShots.map(s => ({
      duration_sec: s.duration_sec || 5,
      clip_path: s.clip_url || '',
    }));
    stage.textContent = '提交合成任务...';
    bar.style.width = '10%';

    const composeRes = await fetch(`${A8_API}/video/compose-premium`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        shots: shotsWithClips,
        // 有声模式：Seedance 原生音频，强制不带外部素材（防无声/快速期上传残留串味）
        audio_path: S.vidGenAudio ? '' : (hasUploadedAudio ? S.uploadedAudio : composeAudioPath),
        srt_path: S.vidGenAudio ? '' : (hasUploadedSrt ? S.uploadedSrt : composeSrtPath),
        task_id: S.scriptTaskId || 'premium_' + Date.now().toString(36),
        parent_task_id: composeParentId,
      }),
    });
    if (!composeRes.ok) throw new Error(apiErrMsg(await composeRes.text()));
    const composeData = await composeRes.json();

    // 轮询合成进度
    await new Promise((resolve, reject) => {
      pollWithProgress(composeData.data.task_id,
        (pct, msg) => { bar.style.width = (pct * 100) + '%'; stage.textContent = msg; },
        (result) => {
          bar.style.width = '100%';
          stage.textContent = (result.quality && result.quality.warnings) ? '合成完成（有质检警告）' : '合成完成';
          const player = document.getElementById('vidPlayer');
          player.src = result.video_path;
          document.getElementById('vidPreview').style.display = '';
          document.getElementById('vidDownload').href = result.video_path;
          showS('vidComposeStatus', 'success', `视频合成完成 · ${result.duration_sec || '?'}s`);
          player.scrollIntoView({ behavior: 'smooth' });
          resolve();
        },
        reject
      );
    });
  } catch(e) { showS('vidComposeStatus', 'error', `合成失败: ${e?.message || e || '未知错误'}`); }
  finally {
    wrap.style.display = 'none';
    btn.disabled = false; btn.textContent = '🎬 合成视频';
  }
}

// 上传自定义图片
async function vidUploadImagesChange() {
  const input = document.getElementById('vidUploadImages');
  const files = input.files;
  if (!files.length) return;
  const zone = document.getElementById('vidUploadSection').querySelector('.upload-zone');
  zone.classList.add('uploading');
  const form = new FormData();
  for (const f of files) form.append('files', f);
  try {
    const res = await fetch(`${A8_API}/video/upload-images`, { method:'POST', body: form });
    if (!res.ok) throw new Error(apiErrMsg(await res.text()));
    const data = await res.json();
    if (!S.uploadedImages) S.uploadedImages = [];
    S.uploadedImages = S.uploadedImages.concat(data.data.images);
    renderUploadedImages();
  } catch(e) { showS('vidComposeStatus', 'error', '图片上传失败: ' + e.message); }
  finally {
    zone.classList.remove('uploading');
    input.value = '';
  }
}

// 渲染已上传图片
function renderUploadedImages() {
  const preview = document.getElementById('vidUploadImagesPreview');
  const zone = document.getElementById('vidUploadSection').querySelector('.upload-zone');
  if (!zone || !preview) return;
  const cnt = (S.uploadedImages || []).length;
  preview.innerHTML = '';
  if (!cnt) {
    zone.querySelector('.upload-zone-icon').textContent = '🖼️';
    zone.querySelector('.upload-zone-title').textContent = '上传图片素材';
    zone.querySelector('.upload-zone-hint').textContent = '点击选择图片 · 支持 JPG/PNG/WebP';
    return;
  }
  S.uploadedImages.forEach((img, i) => {
    const div = document.createElement('div');
    div.className = 'upload-thumb';
    div.innerHTML = '<img src="' + img + '" onerror="this.style.display=\'none\'" onclick="event.stopPropagation();openLightbox(\'' + img + '\')">';
    div.innerHTML += '<button class="upload-thumb-del" onclick="event.stopPropagation();removeUploadedImage(' + i + ')" title="删除">×</button>';
    preview.appendChild(div);
  });
  zone.querySelector('.upload-zone-icon').textContent = '✅';
  zone.querySelector('.upload-zone-title').textContent = cnt + ' 张图片已上传';
  zone.querySelector('.upload-zone-hint').textContent = '点击添加更多';
}


// 上传自定义音频
async function vidUploadAudioChange() {
  const input = document.getElementById('vidUploadAudio');
  const file = input.files[0];
  if (!file) return;
  const zone = document.getElementById('vidAudioZone');
  zone.classList.add('uploading');
  const form = new FormData();
  form.append('file', file);
  try {
    const res = await fetch(`${A8_API}/video/upload-audio`, { method:'POST', body: form });
    if (!res.ok) throw new Error(apiErrMsg(await res.text()));
    const data = await res.json();
    S.uploadedAudio = data.data.audio_path;
    syncAudioCard();  // 隐藏上传框，显示已上传卡片
    const card = document.getElementById('vidUploadAudioCard');
    card.querySelector('.audio-card-name').textContent = file.name;
  } catch(e) { showS('vidComposeStatus', 'error', '音频上传失败: ' + e.message); }
  finally {
    zone.classList.remove('uploading');
    input.value = '';
  }
}

// 删除上传的音频
function removeUploadedAudio() {
  S.uploadedAudio = '';
  syncAudioCard();
}

// 从配音设置一键导入音频和字幕到上传区
function importTtsToCompose() {
  if (!S.audioPath && !S.srtPath) { showS('vidComposeStatus', 'error', '请先在「配音设置」中生成配音'); return; }
  if (S.audioPath) {
    S.uploadedAudio = S.audioPath;
    syncAudioCard();
    const audiocard = document.getElementById('vidUploadAudioCard');
    audiocard.querySelector('.audio-card-name').textContent = '🎙️ ' + (S.audioPath.split('/').pop() || '配音音频');
  }
  if (S.srtPath) {
    S.uploadedSrt = S.srtPath;
    syncSrtCard();
    const srtcard = document.getElementById('vidUploadSrtCard');
    srtcard.querySelector('.audio-card-name').textContent = '📝 ' + (S.srtPath.split('/').pop() || '字幕文件');
  }
  showS('vidComposeStatus', 'success', '已导入配音和字幕');
}

// 将 TTS 生成的镜头导入到精品模式分镜编辑器（覆盖现有）
function importTtsShots() {
  if (!S._pendingShots || !S._pendingShots.length) {
    showS('vidTTSStatus', 'error', '请先生成配音');
    return;
  }
  // 覆盖会丢已生成的视频记录，先确认（无生成记录直接导入）
  const existing = (S.storyboard && S.storyboard.shots || []).filter(s => s.clip_url).length;
  if (existing > 0 && !confirm(`导入将覆盖当前 ${S.storyboard.shots.length} 个分镜（其中 ${existing} 个已生成视频需重新生成），确定？`)) return;
  S.storyboard = { shots: [...S._pendingShots] };
  // 保留 _pendingShots 作为「最新一份配音分组」：可重复导入，重新配音后才更新
  S._diyMode = false;  // 重新导入即退出 DIY，回到配音锁定
  // 绑定当前配音批次：配音更新后未重新导入会被合成拦截
  S._sbTtsTaskId = S.ttsTaskId || null;
  // 清空上传区旧音频/字幕残留，避免覆盖新配音产物
  S.uploadedAudio = '';
  S.uploadedSrt = '';

  // 切到精品模式：有声模式下导入则以配音分组为底稿自由编辑，否则无声导入（锁定）
  const target = S.vidComposeMode === 'premium_audio' ? 'premium_audio' : 'premium';
  document.getElementById('vidCompose').value = target;
  S.vidGenAudio = target === 'premium_audio';
  S.vidComposeMode = target;
  // 补齐精品模式 UI 外壳（从快速模式导入时模型行曾被隐藏、质量检查曾被放开）
  const qualitySel = document.getElementById('vidQuality');
  const aiModelRow = document.getElementById('vidAIModelRow');
  if (qualitySel) { qualitySel.value = 'true'; qualitySel.disabled = true; }
  if (aiModelRow) aiModelRow.style.display = '';

  renderStoryboard();
  document.getElementById('btnCompose').onclick = doComposePremium;
  syncUploadZones();
  document.getElementById('vidTtsShotsCount').textContent = '已导入';
  showS('vidTTSStatus', 'success', `已导入 ${S.storyboard.shots.length} 个镜头`);
}

// SRT 上传
async function vidUploadSrtChange() {
  const input = document.getElementById('vidUploadSrt');
  const file = input.files[0];
  if (!file) return;
  const zone = document.getElementById('vidSrtZone');
  zone.classList.add('uploading');
  const form = new FormData();
  form.append('file', file);
  try {
    const res = await fetch(`${A8_API}/video/upload-srt`, { method:'POST', body: form });
    if (!res.ok) throw new Error(apiErrMsg(await res.text()));
    const data = await res.json();
    S.uploadedSrt = data.data.srt_path;
    syncSrtCard();  // 隐藏上传框，显示已上传卡片
    const card = document.getElementById('vidUploadSrtCard');
    card.querySelector('.audio-card-name').textContent = file.name;
  } catch(e) { showS('vidComposeStatus', 'error', '字幕上传失败: ' + e.message); }
  finally {
    zone.classList.remove('uploading');
    input.value = '';
  }
}

function removeUploadedSrt() {
  S.uploadedSrt = '';
  syncSrtCard();
}

// 删除上传的图片
function removeUploadedImage(index) {
  if (!S.uploadedImages) return;
  S.uploadedImages.splice(index, 1);
  renderUploadedImages();
}

// 合成
async function doCompose() {
  const hasUploadedImages = S.uploadedImages && S.uploadedImages.length;
  if (!hasUploadedImages) { showS('vidComposeStatus', 'error', '请先上传图片或视频素材'); return; }
  const btn = document.getElementById('btnCompose');
  btn.disabled = true; btn.textContent = '⏳ 合成中...';
  document.getElementById('vidComposeStatus').textContent = '';

  // 显示进度条
  const wrap = document.getElementById('vidComposeProgress');
  const bar = document.getElementById('vidComposeBar');
  const stage = document.getElementById('vidComposeStage');
  wrap.style.display = ''; bar.style.width = '0%'; stage.textContent = '准备中...';

  const specRadio = document.querySelector('input[name="vidSpec"]:checked');
  const spec = specRadio ? specRadio.value : '9:16';
  const quality = document.getElementById('vidQuality').value === 'true';
  const imgSrc = S.uploadedImages;
  const hasUploadedAudio = S.uploadedAudio && S.uploadedAudio.length;
  const hasUploadedSrt = S.uploadedSrt && S.uploadedSrt.length;
  const composeOpts = {
    images: imgSrc,
    audio_path: hasUploadedAudio ? S.uploadedAudio : (S.audioPath || ''),
    srt_path: hasUploadedSrt ? S.uploadedSrt : (S.srtPath || ''),
    aspect_ratio: spec,
    resolution: document.getElementById('vidResolution').value,
    transition: document.getElementById('vidTransition').value,
    quality_check: quality,
    parent_task_id: S.ttsTaskId || null,
  };

  try {
    const res = await fetch(`${A8_API}/video/compose`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify(composeOpts),
    });
    if (!res.ok) throw new Error(apiErrMsg(await res.text()));
    const data = await res.json();

    // 轮询合成进度
    await new Promise((resolve, reject) => {
      pollWithProgress(data.data.task_id,
        (pct, msg) => { bar.style.width = (pct * 100) + '%'; stage.textContent = msg; },
        (result) => {
          bar.style.width = '100%'; stage.textContent = '合成完成';
          const vp = result.video_path;
          document.getElementById('vidPlayer').src = vp;
          document.getElementById('vidDownload').href = vp;
          document.getElementById('vidPreview').style.display = '';
          showS('vidComposeStatus', 'success', `视频合成完成 · ${(result.duration_sec || '?').toString()}s`);
          document.getElementById('vidPlayer').scrollIntoView({ behavior: 'smooth' });
          resolve();
        },
        reject
      );
    });
  } catch(e) { showS('vidComposeStatus', 'error', `合成失败: ${e?.message || e || '未知错误'}`); }
  finally {
    wrap.style.display = 'none';
    btn.disabled = false; btn.textContent = '🎬 合成视频';
  }
}

// ══════════════════════════════════════════════════════
//  视频配置初始化

// ══════════════════════════════════════════════════════
//  视频配置初始化
// ══════════════════════════════════════════════════════
function vidInitConfig() {
  // 配音声音列表
  const voices = [
    { v:'zh-CN-XiaoxiaoNeural', n:'晓晓（女）' },
    { v:'zh-CN-YunxiNeural', n:'云希（男）' },
  ];
  const voiceSel = document.getElementById('vidVoice');
  voiceSel.innerHTML = voices.map(v => `<option value="${v.v}">${v.n}</option>`).join('');

  // 语速列表
  const rates = [
    { v:'-30%', n:'慢速 -30%' },
    { v:'-15%', n:'稍慢 -15%' },
    { v:'+0%', n:'正常' },
    { v:'+15%', n:'稍快 +15%' },
    { v:'+30%', n:'快速 +30%' },
  ];
  const rateSel = document.getElementById('vidRate');
  rateSel.innerHTML = rates.map(r => `<option value="${r.v}">${r.n}</option>`).join('');
  rateSel.value = '+0%';

  // 从 localStorage 恢复上次配音设置
  const savedVoice = localStorage.getItem('vidVoice');
  if (savedVoice) voiceSel.value = savedVoice;
  const savedRate = localStorage.getItem('vidRate');
  if (savedRate) rateSel.value = savedRate;

  // 配音设置变更时自动保存
  voiceSel.addEventListener('change', () => localStorage.setItem('vidVoice', voiceSel.value));
  rateSel.addEventListener('change', () => localStorage.setItem('vidRate', rateSel.value));

  // 导出比例
  const specs = [
    { v:'9:16', n:'9:16 竖屏' },
    { v:'16:9', n:'16:9 横屏' },
    { v:'1:1', n:'1:1 方形' },
  ];
  const specsEl = document.getElementById('vidSpecs');
  specsEl.innerHTML = specs.map((s, i) =>
    `<label class="vid-check-item"><input type="radio" name="vidSpec" value="${s.v}" ${i===0?'checked':''}>${s.n}</label>`
  ).join('');

  // 初始化上传区域（仅一次，不受模式切换影响）
  document.getElementById('vidUploadSection').innerHTML = `
    <div style="display:flex;gap:10px;">
      <div id="vidUploadImagesZone" class="upload-zone" onclick="document.getElementById('vidUploadImages').click()" style="flex:1;">
        <div class="upload-zone-icon">🖼️</div>
        <div class="upload-zone-title">上传图片/视频素材</div>
        <div class="upload-zone-hint">点击选择 · 支持 JPG/PNG/MP4</div>
        <input type="file" id="vidUploadImages" multiple accept="image/*,video/*" onchange="vidUploadImagesChange()" style="display:none;">
      </div>
      <div style="flex:1;display:flex;flex-direction:column;">
        <div class="upload-zone" onclick="document.getElementById('vidUploadAudio').click()" id="vidAudioZone" style="flex:1;">
          <div class="upload-zone-icon">🎵</div>
          <div class="upload-zone-title">上传音频素材</div>
          <div class="upload-zone-hint">点击选择音频 · 支持 MP3/WAV</div>
          <input type="file" id="vidUploadAudio" accept="audio/*" onchange="vidUploadAudioChange()" style="display:none;">
        </div>
        <div id="vidUploadAudioCard" class="audio-card" style="display:none;">
          <div class="audio-card-icon">🎵</div>
          <div class="audio-card-info">
            <div class="audio-card-name"></div>
            <div class="audio-card-hint">点击替换音频</div>
          </div>
          <button class="audio-card-del" onclick="event.stopPropagation();removeUploadedAudio()" title="删除">×</button>
        </div>
      </div>
      <div style="flex:1;display:flex;flex-direction:column;">
        <div class="upload-zone" onclick="document.getElementById('vidUploadSrt').click()" id="vidSrtZone" style="flex:1;">
          <div class="upload-zone-icon">📝</div>
          <div class="upload-zone-title">上传字幕文件</div>
          <div class="upload-zone-hint">点击选择字幕 · 支持 SRT</div>
          <input type="file" id="vidUploadSrt" accept=".srt" onchange="vidUploadSrtChange()" style="display:none;">
        </div>
        <div id="vidUploadSrtCard" class="audio-card" style="display:none;">
          <div class="audio-card-icon">📝</div>
          <div class="audio-card-info">
            <div class="audio-card-name"></div>
            <div class="audio-card-hint">点击替换字幕</div>
          </div>
          <button class="audio-card-del" onclick="event.stopPropagation();removeUploadedSrt()" title="删除">×</button>
        </div>
      </div>
    </div>
    <div id="vidUploadImagesPreview" class="upload-preview-row"></div>`;

  // 初始化合成参数
  vidRenderComposeParams();
}

// ══════════════════════════════════════════════════════
//  通用工具
// ══════════════════════════════════════════════════════
// 屏幕中上方浮现、渐隐消失的提示（错误通知）
function showToast(kind, msg) {
  let box = document.getElementById('toastBox');
  if (!box) {
    box = document.createElement('div');
    box.id = 'toastBox';
    document.body.appendChild(box);
  }
  const t = document.createElement('div');
  t.className = 'toast ' + kind;
  t.textContent = msg;
  box.appendChild(t);
  requestAnimationFrame(() => t.classList.add('show'));
  setTimeout(() => {
    t.classList.remove('show');
    setTimeout(() => t.remove(), 350);
  }, 3500);
}
// 从错误响应（文本或已解析对象）提取可读消息：兼容业务 {message} 与 FastAPI {detail}
function apiErrMsg(text) {
  if (text && typeof text === 'object') {
    if (typeof text.message === 'string') return text.message;
    if (typeof text.detail === 'string') return text.detail;
    if (Array.isArray(text.detail)) return text.detail.map(d => d.msg || JSON.stringify(d)).join('; ');
  }
  try {
    const j = JSON.parse(text);
    if (typeof j.message === 'string') return j.message;
    if (typeof j.detail === 'string') return j.detail;
    if (Array.isArray(j.detail)) return j.detail.map(d => d.msg || JSON.stringify(d)).join('; ');
  } catch (_) {}
  return String(text || '请求失败').slice(0, 300);
}
function showS(id, kind, msg) {
  // 错误双通道：toast 悬空提醒 + 状态栏留痕（错过弹窗也能看到）
  const el = document.getElementById(id);
  if (el) { el.className = 'status ' + kind; el.textContent = msg; }
  if (kind === 'error') showToast('error', msg);
}
function esc(s) { if (s == null) return ''; s = String(s); return s.replace(/[&<>`\\]/g, m => m==='&'?'&amp;':(m==='<'?'&lt;':(m==='>'?'&gt;':(m==='`'?'&#96;':'&#92;')))); }

if (typeof marked !== 'undefined') marked.setOptions({ breaks: true, gfm: true, headerIds: false, mangle: false });

// 回车触发抓取
document.getElementById('url1688').addEventListener('keydown', e => { if (e.key === 'Enter') doScrape(); });

// ══════════════════════════════════════════════════════
//  AI 生图 Tab
// ══════════════════════════════════════════════════════
let igRefFiles = [];  // 参考图文件列表

document.getElementById('igRefInput').addEventListener('change', function() {
  for (const f of this.files) {
    if (igRefFiles.length >= 10) break;
    igRefFiles.push(f);
  }
  this.value = '';  // 重置 input 以便重复选同一文件
  renderIgRefPreview();
});

function renderIgRefPreview() {
  const c = document.getElementById('igRefPreview');
  const zone = document.getElementById('igRefZone');
  if (!igRefFiles.length) {
    c.innerHTML = '';
    zone.style.display = '';
    return;
  }
  zone.style.display = 'none';
  let html = '';
  igRefFiles.forEach((f, i) => {
    const url = URL.createObjectURL(f);
    html += `<div style="position:relative;width:68px;height:68px;">
      <img src="${url}" style="width:68px;height:68px;object-fit:cover;border-radius:6px;border:1.5px solid var(--border);cursor:zoom-in;" onclick="openLightbox('${url}')">
      <button onclick="removeIgRef(${i})" style="position:absolute;top:-7px;right:-7px;width:18px;height:18px;border-radius:50%;background:#ef4444;color:#fff;border:2px solid #fff;font-size:11px;line-height:1;cursor:pointer;display:flex;align-items:center;justify-content:center;padding:0;" title="删除">×</button>
    </div>`;
  });
  if (igRefFiles.length < 10) {
    html += `<div onclick="document.getElementById('igRefInput').click()" style="width:68px;height:68px;border:1.5px dashed var(--border);border-radius:6px;display:flex;align-items:center;justify-content:center;cursor:pointer;font-size:22px;color:var(--text3);background:var(--bg);" title="添加更多">+</div>`;
  }
  c.innerHTML = html;
}

function removeIgRef(index) {
  igRefFiles.splice(index, 1);
  renderIgRefPreview();
}

async function doImageGen() {
  const raw = document.getElementById('igPrompts').value.trim();
  if (!raw) { showS('igStatus', 'error', '请先输入至少一条提示词'); return; }
  const prompts = raw.split('\n').map(s => s.trim()).filter(Boolean);
  if (!prompts.length) { showS('igStatus', 'error', '请先输入至少一条提示词'); return; }

  const size = document.getElementById('igSize').value;
  const model = document.getElementById('igModel').value.trim() || 'gpt-image-2';
  const btn = document.getElementById('btnImageGen');
  btn.disabled = true; btn.textContent = '⏳ 生成中...';
  showS('igStatus', 'info', `正在生成 ${prompts.length} 张图片...`);

  const fd = new FormData();
  const specs = prompts.map((p, i) => ({position: i + 1, prompt: p, source: "", type: "standalone"}));
  fd.append('prompts', JSON.stringify(specs));
  fd.append('size', size);
  fd.append('model', model);
  for (const f of igRefFiles) fd.append('ref_images', f);
  console.log('[AI生图] model:', model, '参考图数量:', igRefFiles.length);

  try {
    const res = await fetch('/api/v1/images/generate', { method: 'POST', body: fd });
    const json = await res.json();
    if (!res.ok) throw new Error(apiErrMsg(json));
    pollImageTask(json.data.task_id);
  } catch (e) {
    showS('igStatus', 'error', e.message);
    btn.disabled = false; btn.textContent = '🖼️ 生成图片';
  }
}

function pollImageTask(taskId) {
  const btn = document.getElementById('btnImageGen');
  const poll = setInterval(async () => {
    try {
      const res = await fetch(`/api/v1/tasks/${taskId}`);
      const json = await res.json();
      const d = json.data;
      if (!d) return;
      if (d.status === 'SUCCESS') {
        clearInterval(poll);
        const images = d.result.images || [];
        // 推入图库侧边栏
        images.forEach(img => {
          const src = img.remote_url || '';
          if (src) S._genImages.push({ url: src, type: img.type || 'AI生图', position: img.position, source: 'standalone' });
        });
        renderImageBank();
        showS('igStatus', 'success', '✅ 生成完成，在图库中查看');
        btn.disabled = false; btn.textContent = '🖼️ 生成图片';
      } else if (d.status === 'FAILURE') {
        clearInterval(poll);
        showS('igStatus', 'error', d.error_message || '生成失败');
        btn.disabled = false; btn.textContent = '🖼️ 生成图片';
      }
    } catch (e) { /* keep polling */ }
  }, 2000);
}

function renderImageResults(images) {
  const c = document.getElementById('igResults');
  if (!images || !images.length) { c.innerHTML = '<div style="color:var(--text3);text-align:center;padding:20px;">无结果</div>'; return; }
  let html = '<div class="img-grid">';
  for (const img of images) {
    const src = img.remote_url || '';
    if (src) {
      html += `<div style="position:relative;">
        <img src="${esc(src)}" style="width:100%;border-radius:var(--radius-sm);cursor:zoom-in;" onclick="openLightbox('${esc(src)}')">
        <div style="font-size:11px;color:var(--text3);margin-top:4px;padding:0 4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${esc(img.prompt)}">${esc(img.prompt)}</div>
      </div>`;
    } else {
      html += `<div style="padding:20px;background:var(--bg2);border-radius:var(--radius-sm);text-align:center;color:var(--text3);">
        <div>❌ 生成失败</div>
        <div style="font-size:11px;margin-top:4px;">${esc(img.error)}</div>
      </div>`;
    }
  }
  html += '</div>';
  c.innerHTML = html;
}

function openLightbox(src, filename) {
  const img = document.getElementById('lightboxImg');
  img.src = src;
  img.dataset.filename = filename || '';
  document.getElementById('lightbox').style.display = 'flex';
  document.body.style.overflow = 'hidden';
}
function closeLightbox() {
  document.getElementById('lightbox').style.display = 'none';
  document.body.style.overflow = '';
}
function downloadImage(url, filename) {
  fetch(url)
    .then(r => r.blob())
    .then(blob => {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      a.click();
      URL.revokeObjectURL(a.href);
    })
    .catch(() => {
      // fallback: 直接在新窗口打开
      const a = document.createElement('a');
      a.href = url;
      a.target = '_blank';
      a.download = filename;
      a.click();
    });
}
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeLightbox(); });

// ══════════════════════════════════════════════════════
//  图片素材侧边栏
// ══════════════════════════════════════════════════════
function toggleImageBank() {
  const sidebar = document.getElementById('imgBankSidebar');
  const toggle = document.getElementById('imgBankToggle');
  const isOpen = sidebar.classList.toggle('open');
  toggle.classList.toggle('shifted', isOpen);
  if (isOpen) renderImageBank();
}

function renderImageBank() {
  const list = document.getElementById('imgBankList');
  const count = document.getElementById('imgBankCount');
  if (!list || !count) return;
  const imgs = S._genImages || [];
  count.textContent = `(${imgs.length})`;
  list.innerHTML = imgs.map((img, i) => `
    <div class="img-bank-row">
      <img class="img-bank-thumb" src="${esc(img.url)}" onclick="openLightbox('${esc(img.url)}', '${esc(img.type || img.filename || '')}')"
        onerror="this.style.display='none'" title="${esc(img.type || img.filename || '')}" style="cursor:zoom-in;">
      <div class="img-bank-info">
        <div class="label">${esc(img.type || img.filename || img.source || '未命名')}</div>
        <div class="url-hint" title="${esc(img.url)}">${esc(img.url.substring(0, 45))}...</div>
      </div>
      <button class="img-bank-copy" onclick="copyImageUrl('${esc(img.url)}', this)">📋 复制</button>
    </div>`).join('');
}

async function copyImageUrl(url, btn) {
  try {
    await navigator.clipboard.writeText(url);
    btn.textContent = '✅ 已复制';
    setTimeout(() => { btn.textContent = '📋 复制'; }, 1500);
  } catch {
    // fallback
    const ta = document.createElement('textarea');
    ta.value = url; ta.style.position = 'fixed'; ta.style.left = '-9999px';
    document.body.appendChild(ta); ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    btn.textContent = '✅ 已复制';
    setTimeout(() => { btn.textContent = '📋 复制'; }, 1500);
  }
}

// ══════════════════════════════════════════════════════
//  任务历史
// ══════════════════════════════════════════════════════
let histPage = 0;
const HIST_PS = 15;
const TYPE_LABEL = { scrape:'📦 采集', analysis:'📊 分析', strategy:'🎯 策略', image_gen:'🖼️ 生图', script_gen:'📝 脚本', tts:'🔊 配音', video_compose:'🎬 合成', shot_gen:'🎥 分镜' };
const STATUS_BADGE = { PENDING:'⏳', RUNNING:'🔄', SUCCESS:'✅', FAILURE:'❌' };
const STATUS_COLOR = { PENDING:'#888', RUNNING:'#2196F3', SUCCESS:'#4CAF50', FAILURE:'#f44336' };

async function loadHistory() {
  const type = document.getElementById('histType').value;
  const status = document.getElementById('histStatusFilter').value;
  const params = new URLSearchParams({ limit: HIST_PS, offset: histPage * HIST_PS });
  if (type) params.set('type', type);
  if (status) params.set('status', status);
  try {
    const res = await fetch(`${A8_API}/tasks?${params}`);
    const payload = await res.json();
    if (!payload.data) { showS('histStatusMsg','error', payload.message || '无数据'); return; }
    const d = payload.data;
    document.getElementById('histBody').innerHTML = (d.tasks||[]).map(t => {
      const preview = t.status === 'SUCCESS' ? _histPreview(t) : (t.error_message || '—');
      return `<tr style="border-bottom:1px solid var(--border);color:var(--text);">
        <td style="padding:6px 8px;white-space:nowrap;font-size:11px;color:var(--text2);">${(t.created_at||'').slice(0,16).replace('T',' ')}</td>
        <td style="padding:6px 8px;white-space:nowrap;font-size:11px;font-family:monospace;color:var(--text3);">${(t.task_id||'').slice(0,8)}</td>
        <td style="padding:6px 8px;white-space:nowrap;">${TYPE_LABEL[t.type]||t.type||'—'}</td>
        <td style="padding:6px 8px;white-space:nowrap;font-weight:600;color:${STATUS_COLOR[t.status]||'#888'};">${STATUS_BADGE[t.status]||''} ${t.status}</td>
        <td style="padding:6px 8px;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:11px;" title="${esc(preview)}">${esc(preview)}</td>
      </tr>`;
    }).join('') || '<tr><td colspan="5" style="padding:20px;text-align:center;color:var(--text3);">暂无任务记录</td></tr>';
    const totalPages = Math.ceil((d.total||0) / HIST_PS);
    document.getElementById('histPageInfo').textContent = `共 ${d.total} 条 · 第 ${histPage+1}/${totalPages||1} 页`;
    document.getElementById('histPrev').disabled = histPage <= 0;
    document.getElementById('histNext').disabled = histPage >= totalPages - 1;
    showS('histStatusMsg','');
  } catch(e) {
    showS('histStatusMsg','error','加载失败: ' + e.message);
  }
}

function _histPreview(t) {
  try {
    if (t.type === 'scrape') return `采集完成 · ${t.result_json?.image_count||0} 张`;
    if (t.type === 'video_compose') return `视频已生成 · ${t.result_json?.duration_sec?.toFixed(1)||'?'}秒`;
    if (t.type === 'script_gen') return '脚本已生成';
    if (t.type === 'tts') return '配音已生成';
    if (t.type === 'analysis') return '分析完成';
    if (t.type === 'strategy') return '策略已生成';
    if (t.type === 'image_gen') return '图片已生成';
    return '完成';
  } catch(_) { return '完成'; }
}

function prevPage() { if (histPage > 0) { histPage--; loadHistory(); } }
function nextPage() { histPage++; loadHistory(); }

function exportCSV() {
  const type = document.getElementById('histType').value;
  const status = document.getElementById('histStatusFilter').value;
  const params = new URLSearchParams();
  if (type) params.set('type', type);
  if (status) params.set('status', status);
  const a = document.createElement('a');
  a.href = `${A8_API}/tasks/export?${params}`;
  a.download = 'tasks_export.csv';
  a.click();
  showS('histStatusMsg','success','导出中…');
}

// 初始化
vidInitConfig();
switchTab('tabScrape');
