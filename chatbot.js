/* AIPSU Chatbot popout. Usage:
 *   <link rel="stylesheet" href="chatbot.css">
 *   <script src="chatbot.js"></script>
 *   <script>ChatbotPopout.init({ title: 'Assistant', onMessage: async (text, history) => 'reply' });</script>
 * onMessage receives the visitor's text and the message history and returns
 * (or resolves to) the assistant's reply. Without it, a placeholder reply is shown.
 */
(function (global) {
  'use strict';

  var ICON = {
    chat: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"></path>',
    close: '<path d="M6 6l12 12"></path><path d="M18 6L6 18"></path>',
    down: '<path d="M6 9l6 6 6-6"></path>',
    send: '<path d="M12 19V5"></path><path d="M6 11l6-6 6 6"></path>'
  };
  function svg(name, size, cls) {
    return '<svg class="' + (cls || '') + '" width="' + size + '" height="' + size +
      '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      ICON[name] + '</svg>';
  }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined) node.textContent = text; // textContent: never inject message text as HTML
    return node;
  }

  function init(options) {
    var opts = Object.assign({
      title: 'Assistant',
      status: 'Online now',
      greeting: 'Hi! I can answer questions about this site. What would you like to know?',
      placeholder: 'Type your question…',
      note: '',
      suggestions: ['What can you help with?', 'Talk to a person', 'Find a page'],
      startOpen: false,
      onMessage: null
    }, options || {});

    var history = [];
    var root = el('div', 'cb-root');

    var panel = el('div', 'cb-panel');
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-label', opts.title);

    var header = el('div', 'cb-header');
    var avatar = el('div', 'cb-avatar');
    avatar.innerHTML = svg('chat', 20);
    var heading = el('div', 'cb-heading');
    heading.appendChild(el('div', 'cb-title', opts.title));
    heading.appendChild(el('div', 'cb-status', opts.status));
    var minimise = el('button', 'cb-minimise cb-on-navy');
    minimise.type = 'button';
    minimise.setAttribute('aria-label', 'Minimise chat');
    minimise.innerHTML = svg('down', 20);
    header.appendChild(avatar); header.appendChild(heading); header.appendChild(minimise);

    var log = el('div', 'cb-log');
    log.setAttribute('aria-live', 'polite');

    var composer = el('div', 'cb-composer');
    var form = el('form', 'cb-form');
    var label = el('label', 'cb-sr', 'Your message');
    label.htmlFor = 'cb-input';
    var input = el('input', 'cb-input');
    input.id = 'cb-input'; input.type = 'text'; input.autocomplete = 'off';
    input.placeholder = opts.placeholder;
    var send = el('button', 'cb-send');
    send.type = 'submit';
    send.setAttribute('aria-label', 'Send message');
    send.innerHTML = svg('send', 20);
    form.appendChild(label); form.appendChild(input); form.appendChild(send);
    composer.appendChild(form);
    if (opts.note) composer.appendChild(el('div', 'cb-note', opts.note));

    panel.appendChild(header); panel.appendChild(log); panel.appendChild(composer);

    var launcher = el('button', 'cb-launcher');
    launcher.type = 'button';
    launcher.innerHTML = svg('chat', 24, 'cb-icon-chat') + svg('close', 24, 'cb-icon-close');

    root.appendChild(panel); root.appendChild(launcher);
    document.body.appendChild(root);

    var chips = null;
    function scrollDown() { log.scrollTop = log.scrollHeight; }
    function addMessage(from, text) {
      history.push({ from: from, text: text });
      log.appendChild(el('div', 'cb-msg cb-msg-' + from, text));
      scrollDown();
    }
    function setOpen(open) {
      root.classList.toggle('cb-open', open);
      launcher.setAttribute('aria-label', open ? 'Close chat' : 'Open chat');
      launcher.setAttribute('aria-expanded', String(open));
      if (open) { input.focus(); scrollDown(); } else { launcher.focus(); }
    }
    function submit(text) {
      text = String(text || '').trim();
      if (!text) return;
      if (chips) { chips.remove(); chips = null; }
      addMessage('user', text);
      input.value = '';
      var typing = el('div', 'cb-msg cb-msg-bot cb-typing', 'Typing…');
      log.appendChild(typing); scrollDown();
      var reply = opts.onMessage
        ? Promise.resolve().then(function () { return opts.onMessage(text, history.slice()); })
        : new Promise(function (resolve) {
            setTimeout(function () {
              resolve('Thanks for your question. This is a placeholder reply; connect onMessage to your backend to answer for real.');
            }, 700);
          });
      reply.then(function (answer) {
        typing.remove();
        addMessage('bot', String(answer));
      }).catch(function () {
        typing.remove();
        addMessage('bot', 'Sorry, I could not get an answer just now. Please try again.');
      });
    }

    addMessage('bot', opts.greeting);
    if (opts.suggestions && opts.suggestions.length) {
      chips = el('div', 'cb-chips');
      opts.suggestions.forEach(function (text) {
        var chip = el('button', 'cb-chip', text);
        chip.type = 'button';
        chip.addEventListener('click', function () { submit(text); });
        chips.appendChild(chip);
      });
      log.appendChild(chips);
    }

    launcher.addEventListener('click', function () { setOpen(!root.classList.contains('cb-open')); });
    minimise.addEventListener('click', function () { setOpen(false); });
    form.addEventListener('submit', function (e) { e.preventDefault(); submit(input.value); });
    panel.addEventListener('keydown', function (e) { if (e.key === 'Escape') setOpen(false); });

    launcher.setAttribute('aria-label', 'Open chat');
    launcher.setAttribute('aria-expanded', 'false');
    if (opts.startOpen) root.classList.add('cb-open'), launcher.setAttribute('aria-expanded', 'true'), launcher.setAttribute('aria-label', 'Close chat');

    return {
      open: function () { setOpen(true); },
      close: function () { setOpen(false); },
      send: submit,
      element: root
    };
  }

  global.ChatbotPopout = { init: init };
})(window);
