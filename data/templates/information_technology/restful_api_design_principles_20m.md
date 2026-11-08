---
topic: "RESTful API Design Principles"
Category: "Information Technology"
duration_min: 20
---
Picture an API that works perfectly. Every feature is there. And yet, two days after receiving it, the developer who has to integrate with it sends a polite message: "I'm not sure how this is supposed to work." The endpoint names are inconsistent. Errors come back as two hundred OK, with an error message hidden inside. And every list returns all ten thousand records at once.

Good {{ argument_time_of_day }}, everyone, and thanks for coming to {{ argument_event_or_meetup_name }}. My name is {{ argument_speaker_name }}, and I work as {{ argument_speaker_role }}. That API, which many of us have either received or, if we're honest, built, is a good place to start today's topic: how to design RESTful APIs that other developers actually enjoy using.

The lesson is simple: an API is a user interface. The users just happen to be developers. And like any user interface, it can be clear and predictable, or confusing and frustrating. So today, we'll go through the principles that make the difference.

The route for today runs from what REST actually means, through resources and URLs, HTTP methods and status codes, and practical topics like pagination, filtering, versioning, and error handling, all the way to security, documentation, and the most common mistakes to avoid.

To keep things concrete, I'll use one running example throughout: an online bookstore with books, authors, customers, and orders.

Begin with the basics: what is REST?

REST stands for Representational State Transfer. The term was introduced by Roy Fielding in his doctoral dissertation in the year two thousand. Fielding was also one of the main authors of the HTTP specification, which is why REST fits the web so naturally.

REST is not a protocol, and it's not a library. It's an architectural style, a set of constraints. If an API follows them, we call it RESTful. Five of them matter most.

First, client-server separation. The client, say, a mobile app, and the server evolve independently. The app doesn't care how the server stores data, and the server doesn't care how the app draws its screens.

Second, statelessness. Every request must contain all the information the server needs to process it. The server doesn't remember anything about the client between requests. If you're authenticated, you send your token with every request. This may sound inefficient, but it's what allows us to put ten servers behind a load balancer and send each request to any of them.

Third, cacheability. Responses should say whether they can be cached and for how long. Good caching can remove a huge amount of load from your servers.

Fourth, a uniform interface. This is the heart of REST: we interact with resources through a consistent set of operations, the standard HTTP methods, using standard representations, such as JSON.

And fifth, a layered system. The client doesn't need to know whether it's talking directly to the server or to a proxy, a gateway, or a cache in between.

From theory to practice, then. The first design principle is: think in resources, not actions.

A resource is any concept that's important enough to be named: a book, an author, an order, a customer. In a RESTful design, URLs identify resources, and HTTP methods describe what we do with them.

Instead of URLs like slash getAllBooks, slash createBook, or slash deleteBookById, we use one resource path, slash books, and let the method tell the story. GET slash books returns a list of books. POST slash books creates a new book. GET slash books slash forty-two returns the book with ID forty-two. And DELETE slash books slash forty-two removes it.

A few conventions are hiding in there. We use nouns, not verbs, because the verb is already the HTTP method. We use plural nouns, slash books rather than slash book, for consistency, whether we're talking about the collection or one item in it. And we use lowercase words separated by hyphens if a name has more than one word, as in slash order-items.

What about relationships? If we want all the books written by a specific author, a nested path reads very naturally: GET slash authors slash seven slash books. But a word of caution here: don't nest too deeply. A URL like slash authors slash seven slash books slash forty-two slash reviews slash three slash comments is hard to read and hard to maintain. A good rule of thumb is to nest at most one level. Beyond that, give the resource its own top-level path, like slash reviews slash three.

And what about operations that don't fit nicely into create, read, update, delete? For example, cancelling an order. Some teams model it as a change of state, by updating the order's status field to "cancelled." Others create a sub-resource like POST slash orders slash fifteen slash cancellation. Both are reasonable. What's not reasonable is mixing five different styles in the same API.

That brings us to the second principle: use HTTP methods according to their meaning.

There are five methods you'll use almost every day. GET retrieves data and must never change anything on the server. POST creates a new resource, or triggers a process. PUT replaces a resource completely with the data you send. PATCH updates only part of a resource: just the price of a book, say. And DELETE removes a resource.

Two properties are worth knowing here, because they matter a lot in real systems: safety and idempotency.

A method is safe if it doesn't change anything. GET is safe. Browsers, crawlers, and caches count on that, and call GET requests whenever they want. If your GET endpoint deletes data, and this has happened in real projects, a search engine crawler could wipe your database.

A method is idempotent if calling it once or calling it ten times has the same effect. GET, PUT, and DELETE are idempotent. If you delete book forty-two twice, it's still just deleted. POST, however, is not idempotent: sending the same "create order" request twice may create two orders.

Why does this matter? Because networks fail. A mobile app on a weak connection may send a request, never receive the response, and retry. If the request was idempotent, retrying is harmless. If it wasn't, the customer might be charged twice. For critical POST operations like payments, many well-designed APIs accept an idempotency key, a unique value sent by the client, so the server can recognize and ignore duplicate requests.

The third principle, and one that saves hours of debugging: return meaningful status codes.

Status codes are grouped by their first digit. Codes in the two hundreds mean success. The four hundreds mean the client did something wrong. And the five hundreds mean the server did something wrong.

Within those groups, a handful of codes cover most situations. Two hundred, OK, for a successful read or update. Two oh one, Created, after a successful POST, ideally with a Location header pointing to the new resource. Two oh four, No Content, for a successful delete with nothing to return.

On the client error side: four hundred, Bad Request, when the input is invalid. Four oh one, Unauthorized, when the client isn't authenticated. Four oh three, Forbidden, when the client is authenticated but not allowed to do this. Four oh four, Not Found. Four oh nine, Conflict, when someone tries to register an email that already exists. And four twenty-nine, Too Many Requests, when a client exceeds the rate limit.

And on the server side, five hundred, Internal Server Error, when something unexpected breaks, and five oh three, Service Unavailable, during overload or maintenance.

The single most frustrating anti-pattern here is returning two hundred OK for everything and putting "error: true" in the body. It breaks monitoring tools, it breaks client libraries, and it forces every developer to read the documentation just to know whether a request worked. Let the status code tell the truth.

Fourth: keep your request and response bodies consistent.

Today, JSON is the default format for most APIs. Whatever conventions you choose, choose them once and apply them everywhere. If you use camelCase for field names, like "publishedDate," don't switch to snake_case in another endpoint. Use a standard format for dates, such as ISO eight six oh one, which looks like year, month, day, followed by the time and time zone. And be careful with money: never send prices as floating-point numbers, because they can introduce rounding errors. Send an amount in the smallest unit, like cents, or as a string, together with a currency code.

What happens when our bookstore has two hundred thousand books, and a client calls GET slash books? We definitely shouldn't return all of them. That leads to the fifth principle: support pagination, filtering, and sorting.

For pagination, there are two common approaches. The first is offset pagination, with parameters like page equals three and limit equals twenty. It's simple and lets users jump to any page. However, it becomes slow on very large tables, and if new records are added while someone is browsing, they may see duplicates or miss items.

The second approach is cursor pagination. Instead of a page number, the server returns a cursor, an opaque marker pointing to the last item you received, and the client sends it back to get the next batch. It's faster and stable for large or constantly changing data, like social media feeds. The trade-off is that you can't easily jump to page fifty.

In either case, include useful metadata in the response, such as the total count, or a link to the next page.

While we're talking about large responses, remember the cacheability constraint from earlier. HTTP already gives you tools for it. A Cache-Control header tells clients and proxies how long a response can be reused. And an ETag, a short fingerprint of the response, lets a client ask, "Has this changed since the version I have?" If it hasn't, the server answers with three oh four, Not Modified, and sends no body at all. For data that's read far more often than it changes, like our book catalog, that can remove a large share of the traffic, and make the API feel faster for every user.

For filtering and sorting, query parameters work well and are easy to read. A request might look like this: GET slash books, question mark, genre equals science fiction, and sort equals minus published date, meaning newest first. Some APIs also let clients choose which fields to return, which can save bandwidth on mobile devices.

Principle number six: plan for change with versioning.

Your API will change. The question is whether those changes will break the people who depend on you. The golden rule is that adding things is usually safe, but removing or renaming things is a breaking change. Adding a new optional field won't break existing clients. Renaming "title" to "bookTitle" will break all of them.

When you do need a breaking change, introduce a new version. The most common and most visible approach is to put the version in the URL, like slash v1 slash books and slash v2 slash books. Other teams use a custom header or the Accept header, which keeps URLs cleaner but is less obvious. Whichever you choose, support the old version for a reasonable period, announce the deprecation clearly, and give developers time to migrate.

Seventh: make errors helpful.

A good error response answers three questions: what went wrong, why it went wrong, and how to fix it. Compare these two. The first says: "Error." The second says: "Validation failed: the field 'email' must be a valid email address," and includes a machine-readable error code and the name of the field. The second one saves a developer twenty minutes of guessing.

Use the same error structure across the entire API. There's even a published standard for this, called Problem Details for HTTP APIs, which defines common fields like type, title, status, and detail. And one important caution: never expose internal details, such as stack traces or database messages, in production. They're useless to the client and valuable to attackers.

Eighth, and non-negotiable: build security in from the start.

Always use HTTPS, with no exceptions. Authenticate clients using proven standards. For many APIs, that means tokens sent in the Authorization header, often using OAuth two, and frequently in the form of JSON Web Tokens. Never put tokens, passwords, or other secrets in the URL, because URLs end up in logs, browser history, and analytics tools.

Validate every input on the server, even if the client already validated it. Apply rate limiting to protect your service from abuse and accidental overload, and return four twenty-nine with a Retry-After header when a limit is reached. And check authorization on every request, not just whether a user is logged in, but whether this user is allowed to see this order. A surprising number of real-world data leaks happen because an API returned order number one thousand and one to someone who simply changed the ID in the URL.

And the ninth and final principle: document it as a product.

The best API in the world is useless if nobody understands it. The industry standard here is the OpenAPI Specification, formerly known as Swagger. It describes every endpoint, parameter, and response in a machine-readable format, which can generate interactive documentation, client libraries, and even tests. Good documentation also includes realistic examples, explanations of error codes, and a quick-start guide that lets someone make their first successful call in under five minutes.

One more idea deserves a quick word, because you'll see it in discussions about REST: HATEOAS, which stands for Hypermedia as the Engine of Application State. The idea is that responses include links telling the client what it can do next, much like links on a web page. For example, an order response might include a link to cancel it, but only if it can still be cancelled. Strictly speaking, Fielding considers this essential to REST, but in practice, most public APIs use it lightly or not at all. It's worth knowing, so you can make an informed choice.

Then there are the mistakes that come up again and again in API reviews. Verbs in URLs, like slash getUsers. GET requests that change data. Two hundreds returned for errors. Huge lists with no pagination. Naming and formats that change from one endpoint to the next. Breaking changes without a new version. Vague error messages. And authentication checked, but authorization forgotten.

All nine principles, in one breath. A well-designed RESTful API models resources with clear, plural nouns. It uses HTTP methods according to their meaning, and respects safety and idempotency. It tells the truth with status codes. It's consistent in naming and formats. It handles large data with pagination, filtering, and sorting. It evolves carefully with versioning. It returns errors that help instead of confuse. It's secure by default. And it's documented as if it were a product, because it is one.

If you take one idea home from this talk, let it be this: design your API for the developer who will use it at two in the morning, under deadline pressure, without anyone to ask. If that person can understand it, everyone can.

{{ argument_closing_call_to_action }}

Questions? And if you've survived a truly terrible API, tell me about it.
