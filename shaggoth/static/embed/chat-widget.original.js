/*
 * PurePulse chat bubble — talks to Shaggoth at ai.relayapp.pro.
 *
 * Unlike the docs.relayapp.pro widget, this makes real network calls; there
 * is no canned answer table. Every reply on screen came back from POST /chat.
 *
 * Drop-in:  <script defer src="js/chat-widget.js"></script>
 * No dependencies, no build step, no globals beyond window.PurePulseChat.
 */
(function () {
    'use strict';

    var ENDPOINT = 'https://ai.relayapp.pro/chat';

    // The backend is a self-hosted model on a home server, not a hosted API.
    // Observed cold replies take 13s+, so the ceiling is generous and the
    // typing indicator is not optional -- without it the widget looks hung.
    var TIMEOUT_MS = 60000;

    // Visitors are strangers, and on this endpoint every message feeds the
    // curiosity loop that decides what Shaggoth reads overnight. Opting out
    // keeps the syllabus off the public internet. Flip to true only if you
    // want purepulse.one traffic steering what the model learns.
    var ALLOW_RESEARCH = false;

    var GREETING = "Hey — I'm PurePulse's assistant. Ask me about pricing, timelines, or what goes into a build.";

    var css = [
        '.pp-chat,.pp-chat *{box-sizing:border-box;margin:0;padding:0}',
        '.pp-chat{position:fixed;right:24px;bottom:24px;z-index:9999;',
        "font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;line-height:1.6}",

        /* launcher */
        '.pp-chat__toggle{display:flex;align-items:center;justify-content:center;',
        'width:56px;height:56px;border-radius:100px;cursor:pointer;',
        'background:#fff;color:#080808;border:none;',
        'box-shadow:0 8px 32px rgba(0,0,0,.5);transition:transform .2s ease,opacity .2s ease}',
        '.pp-chat__toggle:hover{transform:scale(1.06)}',
        '.pp-chat__toggle:focus-visible{outline:2px solid #fff;outline-offset:3px}',
        '.pp-chat__toggle svg{width:24px;height:24px;display:block}',

        /* panel */
        '.pp-chat__panel{position:absolute;right:0;bottom:72px;width:380px;max-width:calc(100vw - 32px);',
        'height:540px;max-height:calc(100vh - 120px);display:none;flex-direction:column;overflow:hidden;',
        'background:#0e0e0e;border:1px solid rgba(255,255,255,.08);border-radius:18px;',
        'box-shadow:0 24px 64px rgba(0,0,0,.6)}',
        '.pp-chat--open .pp-chat__panel{display:flex;animation:pp-rise .22s ease}',
        '.pp-chat--open .pp-chat__toggle{opacity:.85}',
        '@keyframes pp-rise{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}',

        /* header */
        '.pp-chat__head{display:flex;align-items:center;gap:10px;padding:16px 18px;',
        'border-bottom:1px solid rgba(255,255,255,.08);flex-shrink:0}',
        '.pp-chat__dot{width:8px;height:8px;border-radius:100px;background:#34d399;flex-shrink:0}',
        '.pp-chat__title{font-size:14px;font-weight:600;color:#fff;letter-spacing:-.01em}',
        '.pp-chat__sub{font-size:12px;color:#666;font-weight:400}',
        '.pp-chat__close{margin-left:auto;background:none;border:none;color:#666;cursor:pointer;',
        'font-size:20px;line-height:1;padding:4px 6px;border-radius:8px}',
        '.pp-chat__close:hover{color:#fff;background:rgba(255,255,255,.055)}',

        /* log */
        '.pp-chat__log{flex:1;overflow-y:auto;padding:18px;display:flex;flex-direction:column;gap:12px;',
        'scrollbar-width:thin;scrollbar-color:rgba(255,255,255,.16) transparent}',
        '.pp-chat__log::-webkit-scrollbar{width:6px}',
        '.pp-chat__log::-webkit-scrollbar-thumb{background:rgba(255,255,255,.16);border-radius:100px}',

        '.pp-msg{max-width:85%;padding:10px 14px;border-radius:18px;font-size:14px;',
        'white-space:pre-wrap;overflow-wrap:anywhere}',
        '.pp-msg--bot{align-self:flex-start;background:rgba(255,255,255,.055);color:#fff;border-bottom-left-radius:6px}',
        '.pp-msg--user{align-self:flex-end;background:#fff;color:#080808;border-bottom-right-radius:6px;font-weight:500}',
        '.pp-msg--error{align-self:flex-start;background:rgba(248,113,113,.1);color:#fca5a5;',
        'border:1px solid rgba(248,113,113,.2);border-bottom-left-radius:6px;font-size:13px}',

        /* typing */
        '.pp-typing{align-self:flex-start;display:flex;gap:4px;padding:12px 14px;',
        'background:rgba(255,255,255,.055);border-radius:18px;border-bottom-left-radius:6px}',
        '.pp-typing span{width:6px;height:6px;border-radius:100px;background:#666;animation:pp-blink 1.4s infinite}',
        '.pp-typing span:nth-child(2){animation-delay:.2s}',
        '.pp-typing span:nth-child(3){animation-delay:.4s}',
        '@keyframes pp-blink{0%,60%,100%{opacity:.25}30%{opacity:1}}',

        /* composer */
        '.pp-chat__form{display:flex;gap:8px;padding:14px;border-top:1px solid rgba(255,255,255,.08);flex-shrink:0}',
        '.pp-chat__input{flex:1;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.08);',
        'border-radius:12px;padding:11px 14px;color:#fff;font-size:14px;font-family:inherit;resize:none;',
        'max-height:96px;min-height:42px}',
        '.pp-chat__input::placeholder{color:#666}',
        '.pp-chat__input:focus{outline:none;border-color:rgba(255,255,255,.16)}',
        '.pp-chat__send{background:#fff;color:#080808;border:none;border-radius:12px;padding:0 16px;',
        'font-size:14px;font-weight:600;font-family:inherit;cursor:pointer;flex-shrink:0}',
        '.pp-chat__send:disabled{opacity:.35;cursor:not-allowed}',

        '.pp-chat__foot{padding:0 14px 12px;font-size:11px;color:#333;text-align:center;flex-shrink:0}',

        '@media (max-width:480px){',
        '.pp-chat{right:16px;bottom:16px}',
        '.pp-chat__panel{width:calc(100vw - 32px);height:calc(100vh - 110px)}}',

        '@media (prefers-reduced-motion:reduce){',
        '.pp-chat *,.pp-chat *::before{animation:none!important;transition:none!important}}'
    ].join('');

    var ICON_CHAT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>';

    function el(tag, cls, text) {
        var n = document.createElement(tag);
        if (cls) n.className = cls;
        // textContent, never innerHTML: replies are model output and are
        // treated as untrusted. Markup in a reply must render as characters.
        if (text != null) n.textContent = text;
        return n;
    }

    // One id per tab. sessionStorage (not localStorage) so closing the tab
    // ends the conversation rather than resuming it days later out of context.
    function sessionId() {
        var KEY = 'pp-chat-session';
        var id;
        try {
            id = sessionStorage.getItem(KEY);
            if (!id) {
                id = 'pp-' + Math.random().toString(36).slice(2, 10) + '-' + Date.now().toString(36);
                sessionStorage.setItem(KEY, id);
            }
        } catch (e) {
            // Private mode / storage disabled: fall back to a per-load id.
            id = 'pp-eph-' + Math.random().toString(36).slice(2, 10);
        }
        return id;
    }

    function build() {
        var style = el('style');
        style.textContent = css;
        document.head.appendChild(style);

        var root = el('div', 'pp-chat');

        var toggle = el('button', 'pp-chat__toggle');
        toggle.type = 'button';
        toggle.innerHTML = ICON_CHAT;           // static, author-controlled markup
        toggle.setAttribute('aria-label', 'Open chat');
        toggle.setAttribute('aria-expanded', 'false');

        var panel = el('div', 'pp-chat__panel');
        panel.setAttribute('role', 'dialog');
        panel.setAttribute('aria-label', 'Chat with PurePulse');

        var head = el('div', 'pp-chat__head');
        var titleWrap = el('div');
        titleWrap.appendChild(el('div', 'pp-chat__title', 'PurePulse Assistant'));
        titleWrap.appendChild(el('div', 'pp-chat__sub', 'Usually replies in a few seconds'));
        var close = el('button', 'pp-chat__close', '×');
        close.type = 'button';
        close.setAttribute('aria-label', 'Close chat');
        head.appendChild(el('div', 'pp-chat__dot'));
        head.appendChild(titleWrap);
        head.appendChild(close);

        var log = el('div', 'pp-chat__log');
        log.setAttribute('role', 'log');
        log.setAttribute('aria-live', 'polite');
        log.setAttribute('aria-atomic', 'false');

        var form = el('form', 'pp-chat__form');
        var input = el('textarea', 'pp-chat__input');
        input.rows = 1;
        input.placeholder = 'Ask about pricing, timelines…';
        input.setAttribute('aria-label', 'Your message');
        var send = el('button', 'pp-chat__send', 'Send');
        send.type = 'submit';
        form.appendChild(input);
        form.appendChild(send);

        var foot = el('div', 'pp-chat__foot', 'AI assistant · may be inaccurate · confirm details with us');

        panel.appendChild(head);
        panel.appendChild(log);
        panel.appendChild(form);
        panel.appendChild(foot);
        root.appendChild(panel);
        root.appendChild(toggle);
        document.body.appendChild(root);

        return { root: root, toggle: toggle, panel: panel, close: close, log: log, form: form, input: input, send: send };
    }

    function init() {
        var ui = build();
        var sid = sessionId();
        var busy = false;
        var greeted = false;
        var typingNode = null;

        function scroll() { ui.log.scrollTop = ui.log.scrollHeight; }

        function push(text, kind) {
            var node = el('div', 'pp-msg pp-msg--' + kind, text);
            ui.log.appendChild(node);
            scroll();
            return node;
        }

        function showTyping() {
            typingNode = el('div', 'pp-typing');
            typingNode.setAttribute('aria-label', 'Assistant is typing');
            for (var i = 0; i < 3; i++) typingNode.appendChild(el('span'));
            ui.log.appendChild(typingNode);
            scroll();
        }

        function hideTyping() {
            if (typingNode && typingNode.parentNode) typingNode.parentNode.removeChild(typingNode);
            typingNode = null;
        }

        function setBusy(state) {
            busy = state;
            ui.send.disabled = state;
            ui.input.disabled = state;
        }

        function open() {
            ui.root.classList.add('pp-chat--open');
            ui.toggle.setAttribute('aria-expanded', 'true');
            ui.toggle.setAttribute('aria-label', 'Close chat');
            if (!greeted) { push(GREETING, 'bot'); greeted = true; }
            ui.input.focus();
        }

        function shut() {
            ui.root.classList.remove('pp-chat--open');
            ui.toggle.setAttribute('aria-expanded', 'false');
            ui.toggle.setAttribute('aria-label', 'Open chat');
            ui.toggle.focus();
        }

        function isOpen() { return ui.root.classList.contains('pp-chat--open'); }

        ui.toggle.addEventListener('click', function () { isOpen() ? shut() : open(); });
        ui.close.addEventListener('click', shut);

        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && isOpen()) shut();
        });

        // Enter sends, Shift+Enter breaks the line.
        ui.input.addEventListener('keydown', function (e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                ui.form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
            }
        });

        ui.input.addEventListener('input', function () {
            ui.input.style.height = 'auto';
            ui.input.style.height = Math.min(ui.input.scrollHeight, 96) + 'px';
        });

        ui.form.addEventListener('submit', function (e) {
            e.preventDefault();
            if (busy) return;
            var text = ui.input.value.trim();
            if (!text) return;

            push(text, 'user');
            ui.input.value = '';
            ui.input.style.height = 'auto';
            setBusy(true);
            showTyping();

            // AbortController rather than a bare fetch: a home-server backend
            // can hang, and a spinner that never resolves is worse than an error.
            var ctrl = new AbortController();
            var timer = setTimeout(function () { ctrl.abort(); }, TIMEOUT_MS);

            fetch(ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: text,
                    session_id: sid,
                    research: ALLOW_RESEARCH
                }),
                signal: ctrl.signal
            }).then(function (res) {
                if (res.status === 429) {
                    var err = new Error('rate-limited');
                    err.code = 429;
                    throw err;
                }
                if (!res.ok) throw new Error('HTTP ' + res.status);
                return res.json();
            }).then(function (data) {
                clearTimeout(timer);
                hideTyping();
                var reply = (data && data.reply) ? String(data.reply).trim() : '';
                if (!reply) {
                    push("I didn't catch that — mind rephrasing?", 'bot');
                } else {
                    push(reply, 'bot');
                }
                setBusy(false);
                if (isOpen()) ui.input.focus();
            }).catch(function (err) {
                clearTimeout(timer);
                hideTyping();
                var msg;
                if (err && err.name === 'AbortError') {
                    msg = 'That took too long to come back. Try again, or email us and a human will pick it up.';
                } else if (err && err.code === 429) {
                    msg = "We're getting a lot of questions right now. Give it a minute and try again.";
                } else {
                    msg = "I can't reach the assistant right now. Try again shortly, or reach out directly and we'll help.";
                }
                push(msg, 'error');
                setBusy(false);
            });
        });

        window.PurePulseChat = { open: open, close: shut, endpoint: ENDPOINT };
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
