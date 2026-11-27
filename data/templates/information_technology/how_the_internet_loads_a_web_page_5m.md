---
topic: "How the Internet Loads a Web Page"
category: "Information Technology"
duration_min: 5
---
You've probably done this a dozen times today without a second thought: you open your browser, type {{ argument_example_website_address }}, press Enter, and about a second later, the page appears. Hello everyone, I'm {{ argument_speaker_name }}, and that one second is our topic today.

It feels instant. It feels simple. But in that one second, your request travels across cities, sometimes across oceans, passes through dozens of machines, and comes back as text, images, and code that your browser assembles into a page. Let's slow that second down and follow it, step by step, like a short journey.

Step one: finding the address.

Computers on the internet don't find each other by names. They use numbers called IP addresses, a bit like phone numbers. A name such as {{ argument_example_website_address }} is easy for humans to remember, but your computer needs the number behind it.

That's the job of the Domain Name System, or DNS. In my view, {{ argument_dns_as_hidden_backbone }}.

Now that your browser knows where the server is, it needs to open a reliable line of communication. On the web, this has traditionally been done with a protocol called TCP. The newest version of HTTP, HTTP/3, uses a newer protocol called QUIC instead, but the idea of first establishing a connection is the same, so we'll follow the classic path. Before any real data is sent, the two sides perform what's called a handshake: your computer says "hello, can we talk?", the server says "yes, I hear you," and your computer confirms. Only then does the conversation begin.

Step four: the server does its work.

On the other side, the server receives the request. For a simple website, it might just pick up a file and send it back. But for most modern sites, like {{ argument_dynamic_site_example }}, a lot happens here: the server runs application code, checks who you are, queries a database, and builds a page specifically for you.

The browser reads the HTML from top to bottom and turns it into a tree structure called the DOM, the Document Object Model. It represents every heading, paragraph, button, and image on the page.

JavaScript can then change the page while you use it: opening menus, loading new posts as you scroll, or updating a shopping cart without reloading the page.

The second is the Content Delivery Network, or CDN. I would argue that {{ argument_cdn_value }}.

And modern versions of HTTP allow many files to be sent over the same connection at once, instead of waiting in line.

There's a quiet lesson hidden in all this. My belief is that {{ argument_layers_of_engineering_lesson }}.

That's the end of the line. If you'd like to revisit any stop along the way, now's the time.
