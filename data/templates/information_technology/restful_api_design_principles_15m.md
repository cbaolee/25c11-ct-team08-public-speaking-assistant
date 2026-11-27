---
topic: "RESTful API Design Principles"
category: "Information Technology"
duration_min: 15
---
Picture an API that works perfectly. Every feature is there. And yet, two days after receiving it, the developer who has to integrate with it sends a polite message: "I'm not sure how this is supposed to work." The endpoint names are inconsistent. Errors come back as two hundred OK, with an error message hidden inside. And every list returns all ten thousand records at once.

Good {{ argument_time_of_day }}, everyone, and thanks for coming to {{ argument_event_or_meetup_name }}. My name is {{ argument_speaker_name }}, and I work as {{ argument_speaker_role }}. That API, which many of us have either received or, if we're honest, built, is a good place to start today's topic: how to design RESTful APIs that other developers actually enjoy using.

The lesson is simple: an API is a user interface. The users just happen to be developers. And like any user interface, it can be clear and predictable, or confusing and frustrating. So today, we'll go through the principles that make the difference.

The route for today runs from what REST actually means, through resources and URLs, HTTP methods and status codes, and practical topics like pagination, filtering, versioning, and error handling, all the way to security, documentation, and the most common mistakes to avoid.

Begin with the basics: what is REST?

REST is not a protocol, and it's not a library. It's an architectural style, a set of constraints. If an API follows them, we call it RESTful. Five of them matter most.

Second, statelessness. In my view, {{ argument_statelessness_value }}.

Third, cacheability. Responses should say whether they can be cached and for how long. Good caching can remove a huge amount of load from your servers.

Fourth, a uniform interface. This is the heart of REST: we interact with resources through a consistent set of operations, the standard HTTP methods, using standard representations, such as JSON.

From theory to practice, then. The first design principle is: think in resources, not actions.

Instead of URLs like slash getAllBooks, slash createBook, or slash deleteBookById, we use one resource path, slash books, and let the method tell the story. GET slash books returns a list of books. POST slash books creates a new book. GET slash books slash forty-two returns the book with ID forty-two. And DELETE slash books slash forty-two removes it.

What about relationships? If we want all the books written by a specific author, a nested path reads very naturally: GET slash authors slash seven slash books. But a word of caution here: don't nest too deeply. A URL like slash authors slash seven slash books slash forty-two slash reviews slash three slash comments is hard to read and hard to maintain. A good rule of thumb is to nest at most one level. Beyond that, give the resource its own top-level path, like slash reviews slash three.

That brings us to the second principle: use HTTP methods according to their meaning.

There are five methods you'll use almost every day. GET retrieves data and must never change anything on the server. POST creates a new resource, or triggers a process. PUT replaces a resource completely with the data you send. PATCH updates only part of a resource: just the price of a book, say. And DELETE removes a resource.

A method is safe if it doesn't change anything. GET is safe. Browsers, crawlers, and caches count on that, and call GET requests whenever they want. If your GET endpoint deletes data, and this has happened in real projects, a search engine crawler could wipe your database.

Why does this matter? I would argue that {{ argument_idempotency_matters }}.

The third principle, and one that saves hours of debugging: return meaningful status codes.

Within those groups, a handful of codes cover most situations. Two hundred, OK, for a successful read or update. Two oh one, Created, after a successful POST, ideally with a Location header pointing to the new resource. Two oh four, No Content, for a successful delete with nothing to return.

On the client error side: four hundred, Bad Request, when the input is invalid. Four oh one, Unauthorized, when the client isn't authenticated. Four oh three, Forbidden, when the client is authenticated but not allowed to do this. Four oh four, Not Found. Four oh nine, Conflict, when someone tries to register an email that already exists. And four twenty-nine, Too Many Requests, when a client exceeds the rate limit.

The single most frustrating anti-pattern here is returning two hundred OK for everything and putting "error: true" in the body. My position is that {{ argument_honest_status_codes }}.

Fourth: keep your request and response bodies consistent.

What happens when our bookstore has two hundred thousand books, and a client calls GET slash books? We definitely shouldn't return all of them. That leads to the fifth principle: support pagination, filtering, and sorting.

The second approach is cursor pagination. Instead of a page number, the server returns a cursor, an opaque marker pointing to the last item you received, and the client sends it back to get the next batch. It's faster and stable for large or constantly changing data, like social media feeds. The trade-off is that you can't easily jump to page fifty.

While we're talking about large responses, remember the cacheability constraint from earlier. HTTP already gives you tools for it. A Cache-Control header tells clients and proxies how long a response can be reused. And an ETag, a short fingerprint of the response, lets a client ask, "Has this changed since the version I have?" If it hasn't, the server answers with three oh four, Not Modified, and sends no body at all. For data that's read far more often than it changes, like our book catalog, that can remove a large share of the traffic, and make the API feel faster for every user.

For filtering and sorting, query parameters work well and are easy to read. A request might look like this: GET slash books, question mark, genre equals science fiction, and sort equals minus published date, meaning newest first. Some APIs also let clients choose which fields to return, which can save bandwidth on mobile devices.

Your API will change. The question is whether those changes will break the people who depend on you. I believe that {{ argument_backward_compatibility_view }}.

When you do need a breaking change, introduce a new version. The most common and most visible approach is to put the version in the URL, like slash v1 slash books and slash v2 slash books. Other teams use a custom header or the Accept header, which keeps URLs cleaner but is less obvious. Whichever you choose, support the old version for a reasonable period, announce the deprecation clearly, and give developers time to migrate.

A good error response answers three questions: what went wrong, why it went wrong, and how to fix it. Compare these two. The first says: "Error." The second says: "Validation failed: the field 'email' must be a valid email address," and includes a machine-readable error code and the name of the field. The second one saves a developer twenty minutes of guessing.

Eighth, and non-negotiable: build security in from the start.

Always use HTTPS, with no exceptions. Authenticate clients using proven standards. For many APIs, that means tokens sent in the Authorization header, often using OAuth two, and frequently in the form of JSON Web Tokens. Never put tokens, passwords, or other secrets in the URL, because URLs end up in logs, browser history, and analytics tools.

And the ninth and final principle: document it as a product.

One more idea deserves a quick word, because you'll see it in discussions about REST: HATEOAS, which stands for Hypermedia as the Engine of Application State. The idea is that responses include links telling the client what it can do next, much like links on a web page. For example, an order response might include a link to cancel it, but only if it can still be cancelled. Strictly speaking, Fielding considers this essential to REST, but in practice, most public APIs use it lightly or not at all. It's worth knowing, so you can make an informed choice.

All nine principles, in one breath. A well-designed RESTful API models resources with clear, plural nouns. It uses HTTP methods according to their meaning, and respects safety and idempotency. It tells the truth with status codes. It's consistent in naming and formats. It handles large data with pagination, filtering, and sorting. It evolves carefully with versioning. It returns errors that help instead of confuse. It's secure by default. And it's documented as if it were a product, because it is one.

{{ argument_closing_call_to_action }}

Questions? And if you've survived a truly terrible API, tell me about it.
