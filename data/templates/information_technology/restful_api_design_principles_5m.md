---
topic: "RESTful API Design Principles"
category: "Information Technology"
duration_min: 5
---
Picture an API that works perfectly. Every feature is there. And yet, two days after receiving it, the developer who has to integrate with it sends a polite message: "I'm not sure how this is supposed to work." The endpoint names are inconsistent. Errors come back as two hundred OK, with an error message hidden inside. And every list returns all ten thousand records at once.

Good {{ argument_time_of_day }}, everyone, and thanks for coming to {{ argument_event_or_meetup_name }}. My name is {{ argument_speaker_name }}, and I work as {{ argument_speaker_role }}. That API, which many of us have either received or, if we're honest, built, is a good place to start today's topic: how to design RESTful APIs that other developers actually enjoy using.

The lesson is simple: an API is a user interface. The users just happen to be developers. And like any user interface, it can be clear and predictable, or confusing and frustrating. So today, we'll go through the principles that make the difference.

Second, statelessness. In my view, {{ argument_statelessness_value }}.

Fourth, a uniform interface. This is the heart of REST: we interact with resources through a consistent set of operations, the standard HTTP methods, using standard representations, such as JSON.

That brings us to the second principle: use HTTP methods according to their meaning.

Why does this matter? I would argue that {{ argument_idempotency_matters }}.

On the client error side: four hundred, Bad Request, when the input is invalid. Four oh one, Unauthorized, when the client isn't authenticated. Four oh three, Forbidden, when the client is authenticated but not allowed to do this. Four oh four, Not Found. Four oh nine, Conflict, when someone tries to register an email that already exists. And four twenty-nine, Too Many Requests, when a client exceeds the rate limit.

The single most frustrating anti-pattern here is returning two hundred OK for everything and putting "error: true" in the body. My position is that {{ argument_honest_status_codes }}.

While we're talking about large responses, remember the cacheability constraint from earlier. HTTP already gives you tools for it. A Cache-Control header tells clients and proxies how long a response can be reused. And an ETag, a short fingerprint of the response, lets a client ask, "Has this changed since the version I have?" If it hasn't, the server answers with three oh four, Not Modified, and sends no body at all. For data that's read far more often than it changes, like our book catalog, that can remove a large share of the traffic, and make the API feel faster for every user.

Your API will change. The question is whether those changes will break the people who depend on you. I believe that {{ argument_backward_compatibility_view }}.

Always use HTTPS, with no exceptions. Authenticate clients using proven standards. For many APIs, that means tokens sent in the Authorization header, often using OAuth two, and frequently in the form of JSON Web Tokens. Never put tokens, passwords, or other secrets in the URL, because URLs end up in logs, browser history, and analytics tools.

{{ argument_closing_call_to_action }}

Questions? And if you've survived a truly terrible API, tell me about it.
