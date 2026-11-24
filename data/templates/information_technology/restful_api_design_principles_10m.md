---
topic: "RESTful API Design Principles"
category: "Information Technology"
duration_min: 10
---
Picture an API that works perfectly. Every feature is there. And yet, two days after receiving it, the developer who has to integrate with it sends a polite message: "I'm not sure how this is supposed to work." The endpoint names are inconsistent. Errors come back as two hundred OK, with an error message hidden inside. And every list returns all ten thousand records at once.

Good {{ argument_time_of_day }}, everyone, and thanks for coming to {{ argument_event_or_meetup_name }}. My name is {{ argument_speaker_name }}, and I work as {{ argument_speaker_role }}. That API, which many of us have either received or, if we're honest, built, is a good place to start today's topic: how to design RESTful APIs that other developers actually enjoy using.

The lesson is simple: an API is a user interface. The users just happen to be developers. And like any user interface, it can be clear and predictable, or confusing and frustrating. So today, we'll go through the principles that make the difference.

To keep things concrete, I'll use one running example throughout: an online bookstore with books, authors, customers, and orders.

REST is not a protocol, and it's not a library. It's an architectural style, a set of constraints. If an API follows them, we call it RESTful. Five of them matter most.

Second, statelessness. In my view, {{ argument_statelessness_value }}.

Fourth, a uniform interface. This is the heart of REST: we interact with resources through a consistent set of operations, the standard HTTP methods, using standard representations, such as JSON.

A resource is any concept that's important enough to be named: a book, an author, an order, a customer. In a RESTful design, URLs identify resources, and HTTP methods describe what we do with them.

What about relationships? If we want all the books written by a specific author, a nested path reads very naturally: GET slash authors slash seven slash books. But a word of caution here: don't nest too deeply. A URL like slash authors slash seven slash books slash forty-two slash reviews slash three slash comments is hard to read and hard to maintain. A good rule of thumb is to nest at most one level. Beyond that, give the resource its own top-level path, like slash reviews slash three.

That brings us to the second principle: use HTTP methods according to their meaning.

A method is safe if it doesn't change anything. GET is safe. Browsers, crawlers, and caches count on that, and call GET requests whenever they want. If your GET endpoint deletes data, and this has happened in real projects, a search engine crawler could wipe your database.

Why does this matter? I would argue that {{ argument_idempotency_matters }}.

Status codes are grouped by their first digit. Codes in the two hundreds mean success. The four hundreds mean the client did something wrong. And the five hundreds mean the server did something wrong.

And on the server side, five hundred, Internal Server Error, when something unexpected breaks, and five oh three, Service Unavailable, during overload or maintenance.

The single most frustrating anti-pattern here is returning two hundred OK for everything and putting "error: true" in the body. My position is that {{ argument_honest_status_codes }}.

What happens when our bookstore has two hundred thousand books, and a client calls GET slash books? We definitely shouldn't return all of them. That leads to the fifth principle: support pagination, filtering, and sorting.

In either case, include useful metadata in the response, such as the total count, or a link to the next page.

For filtering and sorting, query parameters work well and are easy to read. A request might look like this: GET slash books, question mark, genre equals science fiction, and sort equals minus published date, meaning newest first. Some APIs also let clients choose which fields to return, which can save bandwidth on mobile devices.

Your API will change. The question is whether those changes will break the people who depend on you. I believe that {{ argument_backward_compatibility_view }}.

Seventh: make errors helpful.

Eighth, and non-negotiable: build security in from the start.

And the ninth and final principle: document it as a product.

Then there are the mistakes that come up again and again in API reviews. Verbs in URLs, like slash getUsers. GET requests that change data. Two hundreds returned for errors. Huge lists with no pagination. Naming and formats that change from one endpoint to the next. Breaking changes without a new version. Vague error messages. And authentication checked, but authorization forgotten.

{{ argument_closing_call_to_action }}

Questions? And if you've survived a truly terrible API, tell me about it.
