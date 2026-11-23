---
topic: "Core Data Structures Workshop: Arrays, Lists, Stacks, Queues and Hash Tables"
category: "Information Technology"
duration_min: 5
---
Good {{ argument_time_of_day }}, everyone, and welcome to {{ argument_workshop_name }}. I'm {{ argument_speaker_name }}, and for the next twenty minutes, we're going to explore the core data structures that almost every program relies on: arrays, linked lists, stacks, queues, and hash tables.

To set the scene: one hundred thousand books piled randomly on the floor. Or the same hundred thousand books, sorted on shelves, with a catalog at the entrance. Same books, but a very different afternoon if you need to find one. Keep those two libraries in mind, because they hold the whole idea of today's session.

A word on how this workshop will work. This is not a lecture where I talk and you listen. Every few minutes, I'll give you a small challenge to think about with the person next to you. There are no wrong answers in these moments. Data structures are much easier to understand when you reason about them yourself, rather than just memorizing definitions.

Why do data structures matter at all? Go back to those two libraries. My view is that {{ argument_why_data_structures_matter }}.

Take a row of ten lockers, all full, holding names in alphabetical order. A new student arrives, and their name needs to go in position zero, at the very beginning, to keep the order. What has to happen to the other nine names? Take thirty seconds and discuss it with your neighbor.

Most modern languages also give us dynamic arrays, like lists in Python, ArrayList in Java, or vectors in C plus plus. I would argue that {{ argument_dynamic_array_tradeoff }}.

Quick question for everyone, and just shout out the answer: if I want the five hundredth item in a linked list, can I jump straight to it like an array?

A queue is the opposite: first in, first out, exactly like a line at a coffee shop. New people join at the back, and people leave from the front. Enqueue adds an item to the back, and dequeue removes one from the front, both in O of one. Queues appear whenever we need fairness, or need to process things in the order they arrived: documents waiting to be printed, messages waiting for a server, customers waiting in an online ticket system.

What are hash tables bad at? In my opinion, {{ argument_hash_table_limits }}.

All right. Time to put everything together. This is the main exercise of today's workshop.

Okay, let's bring it back together and check the answers.

Three takeaways to carry out of this room. Above all, I believe {{ argument_choosing_structures_by_operations }}.

{{ argument_hands_on_lab_instructions }}

You did the thinking today, and it showed. Before we move on, what's still unclear?
