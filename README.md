# AIPSU Chatbot popout

A navy and white chat assistant that pops out over any website: a launcher in the bottom-right corner, a panel with a header, a scrolling message area, and a conversation container (input and send) pinned to the bottom. No dependencies.

## Files

- `chatbot.css`: styles. Colour, radius and shadow tokens are CSS variables on `.cb-root`.
- `chatbot.js`: the widget. Exposes `window.ChatbotPopout`.
- `index.html`: a demo host page.

## Use it

```html
<link rel="stylesheet" href="chatbot.css">
<script src="chatbot.js"></script>
<script>
  ChatbotPopout.init({
    title: 'Assistant',
    onMessage: async (text, history) => {
      // call your backend here and return the reply as a string
    }
  });
</script>
```

Options: `title`, `status`, `greeting`, `placeholder`, `note`, `suggestions` (array of chip labels), `startOpen`, `onMessage`. Without `onMessage` the widget shows a placeholder reply.

`init` returns `{ open(), close(), send(text), element }`.

Open `index.html` in a browser to try it.
