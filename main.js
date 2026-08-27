// KTSD Meeting Poll Interactive Scripts

document.addEventListener('DOMContentLoaded', () => {
  const optionsContainer = document.getElementById('options-container');
  const addOptionBtn = document.getElementById('add-option-btn');
  const autoGenBtn = document.getElementById('auto-gen-btn');
  const autoDateInput = document.getElementById('auto-gen-date');
  const durationSelect = document.getElementById('meeting-duration');
  const clearAllBtn = document.getElementById('clear-all-btn');

  // Helper: Format minutes into HH:MM string
  function formatTime(minutes) {
    const hrs = Math.floor(minutes / 60);
    const mins = minutes % 60;
    const hrsStr = hrs < 10 ? '0' + hrs : hrs;
    const minsStr = mins < 10 ? '0' + mins : mins;
    return `${hrsStr}:${minsStr}`;
  }

  // 1. Dynamic Date Option Row Creation
  if (addOptionBtn && optionsContainer) {
    addOptionBtn.addEventListener('click', () => {
      createOptionRow();
    });

    optionsContainer.addEventListener('click', (e) => {
      if (e.target.closest('.btn-remove-row')) {
        const rows = optionsContainer.querySelectorAll('.option-row');
        if (rows.length > 1) {
          e.target.closest('.option-row').remove();
        } else {
          alert('En az 1 adet tarih seçeneği kalmalıdır.');
        }
      }
    });
  }

  function createOptionRow(dateVal = '', timeVal = '') {
    if (!optionsContainer) return;
    const newRow = document.createElement('div');
    newRow.className = 'option-row';
    newRow.innerHTML = `
      <div>
        <label style="font-size: 0.75rem; color: #64748B; font-weight: 600; display: block; margin-bottom: 0.2rem;">TARİH</label>
        <input type="date" name="option_date[]" class="form-control" value="${dateVal}" required>
      </div>
      <div>
        <label style="font-size: 0.75rem; color: #64748B; font-weight: 600; display: block; margin-bottom: 0.2rem;">SAAT ARALIĞI</label>
        <input type="text" name="option_time[]" class="form-control" value="${timeVal}" placeholder="Örn: 10:00 - 11:00">
      </div>
      <div style="margin-top: 1rem;">
        <button type="button" class="btn-remove-row" title="Seçeneği Sil">
          <i class="fas fa-trash-alt"></i> ×
        </button>
      </div>
    `;
    optionsContainer.appendChild(newRow);
  }

  // 2. Automatic Time Slots Generator (09:00 - 17:00)
  if (autoGenBtn && autoDateInput && durationSelect) {
    autoGenBtn.addEventListener('click', () => {
      const selectedDate = autoDateInput.value;
      if (!selectedDate) {
        alert('Lütfen önce otomatik saat üretilecek tarihi seçiniz.');
        autoDateInput.focus();
        return;
      }

      const durationMinutes = parseInt(durationSelect.value, 10) || 60;
      
      // Clear existing empty default rows if any
      const existingRows = optionsContainer.querySelectorAll('.option-row');
      let clearedCount = 0;
      existingRows.forEach(row => {
        const dInput = row.querySelector('input[type="date"]');
        const tInput = row.querySelector('input[type="text"]');
        if (!dInput.value && !tInput.value) {
          row.remove();
          clearedCount++;
        }
      });

      // Generate slots from 09:00 (540 mins) to 17:00 (1020 mins)
      const startMins = 9 * 60; // 09:00
      const endMins = 17 * 60;  // 17:00

      let generatedCount = 0;
      for (let cur = startMins; cur + durationMinutes <= endMins; cur += durationMinutes) {
        const slotStart = formatTime(cur);
        const slotEnd = formatTime(cur + durationMinutes);
        const timeSlotStr = `${slotStart} - ${slotEnd}`;
        
        createOptionRow(selectedDate, timeSlotStr);
        generatedCount++;
      }

      alert(`Seçilen ${selectedDate} tarihi için 09:00 - 17:00 saatleri arasında ${durationMinutes} dakikalık ${generatedCount} adet saat alternatifi eklendi!`);
    });
  }

  // 3. Clear All Rows
  if (clearAllBtn && optionsContainer) {
    clearAllBtn.addEventListener('click', () => {
      if (confirm('Tüm tarih ve saat seçeneklerini temizlemek istediğinize emin misiniz?')) {
        optionsContainer.innerHTML = '';
        createOptionRow(); // Leave 1 default empty row
      }
    });
  }

  // 4. Interactive Vote Toggle Button State Sync
  const voteToggles = document.querySelectorAll('.btn-vote-toggle');
  voteToggles.forEach(toggle => {
    const radio = toggle.querySelector('input[type="radio"]');
    if (radio && radio.checked) {
      toggle.classList.add('active');
    }

    toggle.addEventListener('click', () => {
      const radioName = radio.getAttribute('name');
      document.querySelectorAll(`input[name="${radioName}"]`).forEach(r => {
        r.closest('.btn-vote-toggle').classList.remove('active');
      });

      radio.checked = true;
      toggle.classList.add('active');
    });
  });

  // 5. Share URL Copying
  const copyBtn = document.getElementById('copy-share-url');
  const shareInput = document.getElementById('share-poll-url');

  if (copyBtn && shareInput) {
    copyBtn.addEventListener('click', () => {
      shareInput.select();
      shareInput.setSelectionRange(0, 99999);
      navigator.clipboard.writeText(shareInput.value).then(() => {
        const originalText = copyBtn.innerHTML;
        copyBtn.innerHTML = '<i class="fas fa-check"></i> Kopyalandı!';
        copyBtn.style.background = '#10B981';
        setTimeout(() => {
          copyBtn.innerHTML = originalText;
          copyBtn.style.background = '';
        }, 2500);
      }).catch(err => {
        alert('Bağlantı kopyalandı!');
      });
    });
  }
});
