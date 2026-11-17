const pages = { '/': 'home', '/uyelik': 'membership', '/salon': 'club' };
const page = document.documentElement.dataset.page || pages[location.pathname.replace(/\/$/, '') || '/'] || 'home';
const whatsappPreview = document.documentElement.dataset.formMode === 'whatsapp';
const languagePicker = document.querySelector('#language');
const localized = [
  ['[data-i18n]', 'i18n', 'textContent'],
  ['[data-aria]', 'aria', 'aria-label'],
  ['[data-placeholder]', 'placeholder', 'placeholder'],
  ['[data-alt]', 'alt', 'alt']
].flatMap(([selector, data, attribute]) => [...document.querySelectorAll(selector)].map(element => ({
  element, attribute, key: element.dataset[data],
  original: attribute === 'textContent' ? element.textContent : element.getAttribute(attribute)
})));

const form = document.querySelector('#registration-form');
const submit = document.querySelector('#submit-lead');
const formStatus = document.querySelector('#registration-status');
const whatsappLink = document.querySelector('#lead-whatsapp');
const contactUrl = document.querySelector('.footer .whatsapp').href;
const fields = Object.fromEntries(['name', 'phone', 'email', 'branch', 'plan', 'consent'].map(name => [name, form.elements.namedItem(name)]));
let language = 'tr';
let errors = {};
let statusKey = '';
let reference = '';
let pending = false;
let lastRequest;

document.querySelector('#preview-form-note').hidden = !whatsappPreview;

for (const section of document.querySelectorAll('[data-pages]')) {
  section.hidden = !section.dataset.pages.split(' ').includes(page);
}

document.querySelector('nav [data-nav="' + page + '"]')?.setAttribute('aria-current', 'page');

function readPreference() {
  try { return localStorage.getItem('workout-language'); } catch { return null; }
}

function translate(key) {
  return translations[language][key] ?? translations.tr[key];
}

function renderFormState() {
  for (const [field, input] of Object.entries(fields)) {
    const error = errors[field];
    input.disabled = pending;
    if (error) input.setAttribute('aria-invalid', 'true');
    else input.removeAttribute('aria-invalid');
    document.getElementById(field + '-error').textContent = error ? translate(error) : '';
  }
  formStatus.textContent = statusKey ? translate(statusKey).replace('{id}', reference) : '';
  formStatus.dataset.state = statusKey;
  submit.disabled = pending;
  submit.textContent = translate(pending ? 'submitting' : whatsappPreview ? 'prepareWhatsApp' : 'submit');
  whatsappLink.hidden = statusKey !== 'readyWhatsApp';
  if (whatsappLink.hidden) whatsappLink.removeAttribute('href');
  else whatsappLink.href = buildWhatsAppUrl();
  form.setAttribute('aria-busy', String(pending));
}

function applyLanguage(nextLanguage) {
  language = Object.hasOwn(translations, nextLanguage) ? nextLanguage : 'tr';
  document.documentElement.lang = language;
  document.documentElement.dir = language === 'ar' ? 'rtl' : 'ltr';
  languagePicker.value = language;

  for (const { element, attribute, key, original } of localized) {
    const value = translations[language][key] ?? original;
    if (attribute === 'textContent') element.textContent = value;
    else element.setAttribute(attribute, value);
  }

  document.title = page === 'home' ? translate('title') : translate(page + 'Page') + ' | Workout Gym';
  document.querySelector('meta[name="description"]').content = translate('description');

  for (const link of document.querySelectorAll('[data-route]')) {
    const url = new URL(link.href);
    if (language === 'tr') url.searchParams.delete('lang');
    else url.searchParams.set('lang', language);
    link.href = url.pathname + url.search + url.hash;
  }

  renderFormState();
}

const requestedLanguage = new URL(location.href).searchParams.get('lang');
applyLanguage(requestedLanguage || readPreference() || 'tr');

languagePicker.addEventListener('change', () => {
  applyLanguage(languagePicker.value);
  try { localStorage.setItem('workout-language', language); } catch {}
  const url = new URL(location.href);
  url.searchParams.set('lang', language);
  history.replaceState(null, '', url);
});

function updatePlanOptions() {
  const campaignAvailable = fields.branch.value === 'circir';
  for (const option of fields.plan.options) {
    option.disabled = Boolean(option.value) && !campaignAvailable;
  }
  if (!campaignAvailable) fields.plan.value = '';
}

for (const link of document.querySelectorAll('[data-plan]')) {
  link.addEventListener('click', () => {
    fields.branch.value = 'circir';
    updatePlanOptions();
    fields.plan.value = link.dataset.plan;
    delete errors.branch;
    delete errors.plan;
    if (!pending) statusKey = '';
    renderFormState();
    fields.name.focus({ preventScroll: true });
  });
}

form.noValidate = true;
for (const input of Object.values(fields)) {
  input.addEventListener('input', () => {
    delete errors[input.name];
    if (input === fields.branch) {
      updatePlanOptions();
      delete errors.plan;
    }
    if (!pending) statusKey = '';
    renderFormState();
  });
}

function normalizePhone(value) {
  return value.trim()
    .replace(/[٠-٩]/g, digit => String(digit.charCodeAt(0) - 0x660))
    .replace(/[۰-۹]/g, digit => String(digit.charCodeAt(0) - 0x6f0));
}

function buildWhatsAppUrl() {
  const lines = [
    translate('whatsappGreeting'),
    '',
    translate('nameLabel') + ': ' + fields.name.value.trim(),
    translate('phoneLabel') + ': ' + normalizePhone(fields.phone.value),
    translate('branchLabel') + ': ' + fields.branch.selectedOptions[0].textContent,
    translate('planLabel') + ': ' + fields.plan.selectedOptions[0].textContent,
  ];
  if (fields.email.value.trim()) lines.push(translate('emailMessageLabel') + ': ' + fields.email.value.trim());
  const url = new URL(contactUrl);
  url.searchParams.set('text', lines.join('\n'));
  return url.href;
}

function validateLead() {
  const name = fields.name.value.trim();
  const phone = normalizePhone(fields.phone.value);
  const email = fields.email.value.trim();
  const branch = fields.branch.value;
  const plan = fields.plan.value;
  const consent = fields.consent.checked;
  const digits = phone.replace(/\D/g, '');

  errors = {};
  if (name.length < 2 || name.length > 100) errors.name = 'errorName';
  if (!/^\+?[\d ().-]+$/.test(phone) || digits.length < 10 || digits.length > 15) errors.phone = 'errorPhone';
  if (email && fields.email.validity.typeMismatch) errors.email = 'errorEmail';
  if (!branch) errors.branch = 'errorBranch';
  if (plan && branch !== 'circir') errors.plan = 'errorPlan';
  if (!consent) errors.consent = 'errorConsent';

  return { name, phone, email, branch, plan, consent, language };
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  if (pending) return;
  const lead = validateLead();
  const firstError = Object.keys(errors)[0];
  if (firstError) {
    statusKey = 'invalid';
    renderFormState();
    fields[firstError].focus();
    return;
  }

  if (whatsappPreview) {
    statusKey = 'readyWhatsApp';
    renderFormState();
    whatsappLink.focus();
    return;
  }

  const { language: leadLanguage, ...contact } = lead;
  const signature = JSON.stringify(contact);
  if (signature !== lastRequest?.signature) lastRequest = { signature, id: crypto.randomUUID() };
  pending = true;
  statusKey = 'submitting';
  renderFormState();

  try {
    const response = await fetch(form.action, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...contact, language: leadLanguage, requestId: lastRequest.id }),
      signal: AbortSignal.timeout(12000)
    });
    const result = await response.json();
    if (response.status === 422 && result.errors) {
      errors = result.errors;
      statusKey = 'invalid';
    } else if (response.ok && result.reference) {
      reference = result.reference;
      statusKey = 'sent';
      form.reset();
      updatePlanOptions();
      lastRequest = null;
    } else {
      statusKey = 'sendError';
    }
  } catch {
    statusKey = 'sendError';
  } finally {
    pending = false;
    renderFormState();
    if (statusKey === 'invalid') fields[Object.keys(errors)[0]]?.focus();
  }
});

const video = document.querySelector('#club-video');
const videoStart = document.querySelector('#video-start');
const videoError = document.querySelector('#video-error');
video.controls = false;

function showVideoError() {
  videoError.hidden = false;
  videoStart.hidden = false;
}

async function startTour() {
  videoError.hidden = true;
  if (video.error || video.networkState === HTMLMediaElement.NETWORK_NO_SOURCE) video.load();
  video.controls = true;
  try { await video.play(); } catch { showVideoError(); }
}

videoStart.addEventListener('click', startTour);
document.querySelector('[data-play-tour]').addEventListener('click', event => {
  if (!event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey) startTour();
});
video.addEventListener('playing', () => {
  const moveFocus = document.activeElement === videoStart;
  videoStart.hidden = true;
  videoError.hidden = true;
  if (moveFocus) video.focus({ preventScroll: true });
});
video.addEventListener('error', showVideoError);
video.querySelector('source').addEventListener('error', showVideoError);
