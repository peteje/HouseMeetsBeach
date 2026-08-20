const API_BASE = '/api';
let captchaToken = '';

async function loadCaptcha(){
  try{
    const res = await fetch(`${API_BASE}/captcha`);
    const data = await res.json();
    captchaToken = data.token;
    document.getElementById('captchaLabel').textContent = `Sicherheitsfrage: ${data.question} = ?`;
  }catch(e){
    document.getElementById('captchaLabel').textContent = 'Sicherheitsfrage (Laden fehlgeschlagen, bitte Seite neu laden)';
  }
}
loadCaptcha();

const form = document.getElementById('rsvpForm');
const msgBox = document.getElementById('formMsg');
const submitBtn = document.getElementById('submitBtn');

form.addEventListener('submit', async function(e){
  e.preventDefault();
  msgBox.className = 'msg';
  msgBox.textContent = '';

  const payload = {
    firstName: document.getElementById('firstName').value.trim(),
    lastName: document.getElementById('lastName').value.trim(),
    email: document.getElementById('email').value.trim(),
    phone: document.getElementById('phone').value.trim(),
    adults: parseInt(document.getElementById('adults').value, 10) || 0,
    children: parseInt(document.getElementById('children').value, 10) || 0,
    notes: document.getElementById('notes').value.trim(),
    foodOrder: document.getElementById('foodOrder').value.trim(),
    website: document.getElementById('website').value,
    captchaToken: captchaToken,
    captchaAnswer: parseInt(document.getElementById('captchaAnswer').value, 10)
  };

  if(!payload.firstName || !payload.lastName || !payload.email || !payload.phone){
    msgBox.className = 'msg error';
    msgBox.textContent = 'Bitte alle Pflichtfelder ausfüllen.';
    return;
  }

  submitBtn.disabled = true;
  submitBtn.textContent = 'Wird gesendet...';

  try{
    const res = await fetch(`${API_BASE}/rsvp`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const data = await res.json();

    if(!res.ok){
      msgBox.className = 'msg error';
      msgBox.textContent = data.detail || 'Da ist etwas schiefgelaufen. Bitte versuche es erneut.';
      submitBtn.disabled = false;
      submitBtn.textContent = 'Verbindlich anmelden';
      loadCaptcha();
      document.getElementById('captchaAnswer').value = '';
      return;
    }

    document.getElementById('successTitle').textContent = data.message || 'Danke für deine Anmeldung!';
    form.style.display = 'none';
    document.getElementById('successState').style.display = 'block';
  }catch(err){
    msgBox.className = 'msg error';
    msgBox.textContent = 'Verbindung fehlgeschlagen. Bitte versuche es erneut.';
    submitBtn.disabled = false;
    submitBtn.textContent = 'Verbindlich anmelden';
  }
});
