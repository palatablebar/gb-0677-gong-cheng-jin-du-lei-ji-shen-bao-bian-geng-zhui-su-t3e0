const notice = document.getElementById('notice');
const holder = document.querySelector('[data-batch]');
const batchId = holder.dataset.batch;

function currentVersion() {
  return parseInt(holder.dataset.version || '0', 10);
}

// 八月批次已闭口，九月为开放承接期；迟到补录登记原属期与承接期。
const LATE_PARAMS = {
  periods: {'2026-08': 'closed', '2026-09': 'open'},
  late_claims: [
    {claim_id: 'L002', period: '2026-08', carry_to: '2026-09'}
  ]
};

async function call(path, method, body) {
  notice.textContent = '处理中…';
  const opt = {method, headers: {'Content-Type': 'application/json'}};
  if (body) opt.body = JSON.stringify(body);
  const res = await fetch(path, opt);
  const data = await res.json();
  if (!res.ok) throw new Error(data.message || ('HTTP ' + res.status));
  return data;
}

function currentVersion() {
  return parseInt(document.body.dataset.version || '0', 10);
}

document.getElementById('prepare').addEventListener('click', async () => {
  try {
    const data = await call('/api/batches', 'POST',
      {sample: document.getElementById('dataset').value, parameters: LATE_PARAMS});
    notice.textContent = '批次已生成：' + data.batch_no;
    window.location.reload();
  } catch (e) { notice.textContent = e.message; }
});

document.getElementById('publish').addEventListener('click', async () => {
  try {
    await call('/api/batches/' + batchId + '/publish', 'POST', {version: currentVersion()});
    notice.textContent = '已发布新版本，旧版快照已留存。';
    window.location.reload();
  } catch (e) { notice.textContent = e.message; }
});

document.getElementById('publish-fail').addEventListener('click', async () => {
  try {
    await call('/api/batches/' + batchId + '/publish', 'POST',
      {version: currentVersion(), fail: true});
  } catch (e) {
    notice.textContent = '发布失败已回滚，上一版保留：' + e.message;
  }
});

document.getElementById('rollback').addEventListener('click', async () => {
  try {
    await call('/api/batches/' + batchId + '/rollback', 'POST', {version: currentVersion()});
    notice.textContent = '当前版已追回，历史快照仍可恢复。';
    window.location.reload();
  } catch (e) { notice.textContent = e.message; }
});

document.querySelectorAll('.restore-btn').forEach(btn => {
  btn.addEventListener('click', async () => {
    try {
      await call('/api/batches/' + batchId + '/restore', 'POST',
        {version: currentVersion(), target_version: parseInt(btn.dataset.version, 10)});
      notice.textContent = '已恢复为历史版本内容，生成新版本，旧版未覆盖。';
      window.location.reload();
    } catch (e) { notice.textContent = e.message; }
  });
});
