---
topic: "SQL vs NoSQL Databases"
category: "Information Technology"
duration_min: 5
---
Here's a decision that takes ten minutes to make at the start of a project, and can take ten months to undo later. Good {{ argument_time_of_day }}, everyone. I'm {{ argument_speaker_name }}, and the decision I mean is this one: should we use a SQL database or a NoSQL database?

You'll find plenty of strong opinions online. Some people say SQL is old-fashioned. My view is that {{ argument_sql_nosql_not_a_war }}.

SQL databases, also known as relational databases, come first.

That last detail is the key idea: tables are connected through relationships. Instead of copying a customer's details into every order, we just store the customer's ID. When we need to see everything together, we use a "join" to combine tables in a single query. And we write those queries in SQL, Structured Query Language, which is powerful, standardized, and known by millions of developers.

The name originally meant "no SQL," but today it's usually read as "not only SQL." It's not one technology, but a family of different approaches that became popular in the late two thousands, when companies like Google, Amazon, and Facebook were dealing with amounts of data and traffic that traditional databases struggled to handle on a single machine.

The third is wide-column stores, like Apache Cassandra, which are designed to handle massive volumes of writes spread across many servers, for example, sensor data or activity logs.

Second, horizontal scaling. Instead of buying one bigger and more expensive server, which we call scaling up, many NoSQL systems are designed to spread data across many ordinary servers, which we call scaling out. Need more capacity? Add more machines.

But there's a trade-off. I would argue that {{ argument_consistency_tradeoff_view }}.

And myth number three: "NoSQL doesn't support transactions." Many modern NoSQL databases now support transactions, and many SQL databases now support flexible JSON data. The line between the two worlds is much blurrier than it used to be.

Is your data's shape changing rapidly, or very different from one record to the next, such as product catalogs with varied attributes or content management? A document database may be easier.

In the real world, many systems use both. In my opinion, {{ argument_polyglot_persistence_view }}.

To bring this closer to home: {{ argument_project_context_example }} Given what we've discussed, the questions to ask are about the structure of the data, how important strict consistency is, and how much the system needs to scale.

Boiled down: SQL databases offer structure, relationships, a powerful query language, and strong guarantees. NoSQL databases offer flexibility and easier horizontal scaling, often in exchange for weaker consistency. The right question is not "which one is better?" but "which one fits this problem, this data, and this team?"

Which database choices have you made in your own projects, and which of them would you make again? I'd like to hear.
