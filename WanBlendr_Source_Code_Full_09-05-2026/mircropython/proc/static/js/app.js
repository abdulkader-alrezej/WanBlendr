// static/js/app.js

function rebootSystem() {
  if (confirm('Are you sure you want to reboot the WanBlendr system?')) {
    fetch('/reboot_system', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      }
    }).then(function(response) {
      if (response.ok) {
        alert('System is rebooting...');
      } else {
        response.text().then(function(t){ alert('Failed to reboot the system. ' + t); });
      }
    }).catch(function(error) {
      alert('Error: ' + error.message);
    });
  }
}

// Lightweight header health updater (safe if elements not present)
(function(){
  var upEl   = document.getElementById('hstrip-uptime');
  var dEl    = document.getElementById('hstrip-date');
  var tEl    = document.getElementById('hstrip-time');
  var mEl    = document.getElementById('hstrip-mem');
  var cEl    = document.getElementById('hstrip-cpu');
  var fEl    = document.getElementById('hstrip-fw');
  var wbEl   = document.getElementById('hstrip-wb');
  var verEl  = document.getElementById('project-ver');
  if(!upEl || !dEl || !tEl || !mEl || !cEl) return;

  // Local clock + uptime interpolation between server polls
  var baseTime = null;        // Date object from last server time
  var baseUptimeSec = 0;      // seconds from last server uptime
  var baseWallTs = 0;         // client ms timestamp when base values captured
  var lastTick = Date.now();  // For debug: tracking main thread freeze
  var isClockSynced = false;  // Flag to indicate if we have a valid base time

  function _pad2(n){ return (n < 10 ? '0' : '') + n; }
  function _formatDate(dt){
    return dt.getFullYear() + '-' + _pad2(dt.getMonth()+1) + '-' + _pad2(dt.getDate());
  }
  function _formatTime(dt){
    return _pad2(dt.getHours()) + ':' + _pad2(dt.getMinutes()) + ':' + _pad2(dt.getSeconds());
  }
  function _parseUptimeSeconds(txt){
    // expects like "1d 2h 3m 4s" or subset; be tolerant
    if(!txt || typeof txt !== 'string') return null;
    if(txt === 'N/A') return null;
    var d = 0, h = 0, m = 0, s = 0;
    var md = txt.match(/(\d+)\s*d/i); if (md) d = parseInt(md[1], 10) || 0;
    var mh = txt.match(/(\d+)\s*h/i); if (mh) h = parseInt(mh[1], 10) || 0;
    var mm = txt.match(/(\d+)\s*m(?!s)/i); if (mm) m = parseInt(mm[1], 10) || 0; // avoid matching 'ms'
    var ms = txt.match(/(\d+)\s*s/i); if (ms) s = parseInt(ms[1], 10) || 0;
    var total = (((d * 24 + h) * 60 + m) * 60 + s);
    // If total is 0 but string was not empty, it might be valid 0s (start) or failed parse
    // But if string contains digits, it's likely valid.
    if(total === 0 && !/\d/.test(txt)) return null;
    return total;
  }
  function _formatUptimeFromSeconds(total){
    if(total === null || typeof total === 'undefined') return '...';
    if(!isFinite(total) || total < 0) total = 0;
    var d = Math.floor(total / 86400);
    total -= d * 86400;
    var h = Math.floor(total / 3600);
    total -= h * 3600;
    var m = Math.floor(total / 60);
    var s = Math.floor(total - m * 60);
    return d + 'd ' + h + 'h ' + m + 'm ' + s + 's';
  }
  function setBaseFromServer(data){
    try{
      var newTime = new Date(String(data.date || '').trim() + 'T' + String(data.time || '').trim());
      if (isNaN(newTime.getTime())) newTime = null;
      
      var newUptime = _parseUptimeSeconds(data.uptime);

      // Decoupled Sync Logic:
      // Once synced, we IGNORE server time updates to prevent jumping/stuttering.
      // We only re-sync if we detect a REBOOT (server uptime dropped significantly).
      
      if(isClockSynced && baseTime){
        // If we have valid uptime data to compare
        if (baseUptimeSec !== null && newUptime !== null) {
          var now = Date.now();
          var deltaMs = now - baseWallTs;
          var currentLocalUptime = baseUptimeSec + Math.floor(deltaMs / 1000);
          
          // Check for Reboot:
          // If server uptime is significantly less than local uptime (e.g. > 60s difference),
          // it means the device restarted. We MUST sync.
          if (newUptime < (currentLocalUptime - 60)) {
              console.warn('⚠️ Device Reboot Detected! Resyncing clock.');
              // Proceed to sync below...
          } else {
              // Otherwise: IGNORE server time. Trust local clock.
              return;
          }
        } else {
          // If uptime is invalid/missing, we cannot verify reboot.
          // Better to keep local clock smooth than to risk jumping.
          return;
        }
      }

      // Hard sync (First time OR Reboot)
      if(newTime) {
          baseTime = newTime;
          if(newUptime !== null) {
            baseUptimeSec = newUptime;
          } else if (baseUptimeSec === null) {
            baseUptimeSec = 0;
          }
          baseWallTs = Date.now();
          isClockSynced = true;
          // console.log('🔄 Clock Synced/Resynced.');
      }

    }catch(e){ console.error('Sync Error:', e); }
  }
  function tickLocalClock(){
    var now = Date.now();
    var diff = now - lastTick;
    if (diff > 1200) {
        console.warn('⚠️ Main Thread FREEZE detected! Delta:', diff, 'ms');
    }
    lastTick = now;

    if(!baseTime) return;
    var deltaMs = now - baseWallTs;
    if (deltaMs < 0) deltaMs = 0;
    var dt = new Date(baseTime.getTime() + deltaMs);
    // Update date/time display
    if (dEl) dEl.textContent = _formatDate(dt);
    if (tEl) tEl.textContent = _formatTime(dt);
    // Update uptime display
    var upSec = baseUptimeSec + Math.floor(deltaMs / 1000);
    if (upEl) upEl.textContent = _formatUptimeFromSeconds(upSec);
  }

  var lastHealthData = {};

  function renderHeaderHealth(d){
    var t0 = Date.now();
    try{
      // Uptime/Date/Time are handled by tickLocalClock using setBaseFromServer(d)
      // So we don't need to update them here to avoid double-paint or jitter.

      // Memory
      var memStr = d.memory_used + ' / ' + d.memory_total + ' MB (' + d.memory_percent + ' %)';
      if(memStr !== lastHealthData.memStr) {
        mEl.textContent = memStr;
        lastHealthData.memStr = memStr;
      }

      // CPU
      var cpuStr = (Math.min(Math.max(d.cpu_usage,0),100)).toFixed(1) + ' %';
      if(cpuStr !== lastHealthData.cpuStr) {
        cEl.textContent = cpuStr;
        lastHealthData.cpuStr = cpuStr;
      }

      // FW
      if (fEl && typeof d.fw_conntrack !== 'undefined') {
        var fwStr = String(d.fw_conntrack);
        if(fwStr !== lastHealthData.fwStr) {
          fEl.textContent = fwStr;
          lastHealthData.fwStr = fwStr;
        }
      }
    }catch(e){ console.error('Render Health Error:', e); }
    var t1 = Date.now();
    if (t1 - t0 > 10) console.log('Render took:', t1 - t0, 'ms');
  }

  function tickHeader(){
    // console.log('🔄 tickHeader Start');
    var tStart = Date.now();
    
    fetch('/dashboard/health/data',{cache:'no-store'})
      .then(function(r){ return r.ok ? r.json() : null; })
      .then(function(d){ 
        // console.log('✅ Health Data Rx', Date.now() - tStart, 'ms');
        if(d){ 
          renderHeaderHealth(d);
          setBaseFromServer(d);
          // tickLocalClock(); // Removed: Main loop handles this.
        } 
      })
      .catch(function(e){ console.error('❌ Health Fetch Error:', e); })
      .finally(function(){
        // Chain the next check to spread load
        if(wbEl){
            setTimeout(function(){
                var tWb = Date.now();
                // console.log('🔄 Fetching WB Status...');
                fetch('/dashboard/wb/status',{cache:'no-store'})
                .then(function(r){ return r.ok ? r.json() : null; })
                .then(function(j){
                    // console.log('✅ WB Status Rx', Date.now() - tWb, 'ms');
                    if(!j) return;
                    var raw = String(j.status || '').trim();
                    // Only update if status changed
                    if(raw !== wbEl.dataset.lastStatus) {
                        var s = raw.toLowerCase();
                        var isRun = (s === 'running');
                        wbEl.textContent = isRun ? 'run' : 'Stop';
                        wbEl.classList.remove('wb-run','wb-stop');
                        wbEl.classList.add(isRun ? 'wb-run' : 'wb-stop');
                        wbEl.dataset.lastStatus = raw;
                    }
                })
                .catch(function(e){ console.error('❌ WB Status Error:', e); });
            }, 200); // 0.2s delay after health
        }
        // Schedule next tick - Reduced to 1.5s for faster updates
        setTimeout(tickHeader, 1500);
      });
  }

  // Fetch version only once
  if(verEl){
    fetch('/dashboard/version',{cache:'no-store'})
      .then(function(r){ return r.ok ? r.json() : null; })
      .then(function(j){
        if(!j) return;
        var v = String(j.version || '').trim();
        if(v){ verEl.textContent = 'ver.' + v; }
      })
      .catch(function(){});
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', tickHeader);
  } else {
    tickHeader();
  }
  
  // Use recursive setTimeout for local clock to prevent main thread blocking
  function runLocalClock(){
    tickLocalClock();
    setTimeout(runLocalClock, 1000);
  }
  runLocalClock();
})();

