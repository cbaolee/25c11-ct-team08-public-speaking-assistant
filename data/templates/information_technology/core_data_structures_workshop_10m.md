---
topic: "Core Data Structures Workshop: Arrays, Lists, Stacks, Queues and Hash Tables"
category: "Information Technology"
duration_min: 10
---
Good {{ argument_time_of_day }}, everyone, and welcome to {{ argument_workshop_name }}. I'm {{ argument_speaker_name }}, and for the next twenty minutes, we're going to explore the core data structures that almost every program relies on: arrays, linked lists, stacks, queues, and hash tables.

To set the scene: one hundred thousand books piled randomly on the floor. Or the same hundred thousand books, sorted on shelves, with a catalog at the entrance. Same books, but a very different afternoon if you need to find one. Keep those two libraries in mind, because they hold the whole idea of today's session.

A word on how this workshop will work. This is not a lecture where I talk and you listen. Every few minutes, I'll give you a small challenge to think about with the person next to you. There are no wrong answers in these moments. Data structures are much easier to understand when you reason about them yourself, rather than just memorizing definitions.

Why do data structures matter at all? Go back to those two libraries. My view is that {{ argument_why_data_structures_matter }}.

To describe speed, we'll use Big-O notation in a very simple way. O of one means the operation takes the same time no matter how much data we have. O of n means the time grows in proportion to the data: twice the data, twice the work. And O of log n means the time grows very slowly, because we cut the problem in half at each step. That's all the theory you need for today.

An array is a collection of items stored one after another, in a continuous block of memory. Picture a row of numbered lockers in a school hallway. Locker zero, locker one, locker two, and so on. Because all the lockers are the same size and sit next to each other, the computer can calculate exactly where any locker is. If you want locker number five hundred, it doesn't need to walk past the first four hundred and ninety-nine. It jumps straight there. Accessing an item by its index is therefore O of one. That's the array's superpower.

Take a row of ten lockers, all full, holding names in alphabetical order. A new student arrives, and their name needs to go in position zero, at the very beginning, to keep the order. What has to happen to the other nine names? Take thirty seconds and discuss it with your neighbor.

Searching is another thing to think about. If the array isn't sorted, you have to check each locker one by one: O of n. But if it's sorted, you can use binary search: open the middle locker, decide whether your name comes before or after it, and throw away half of the lockers each time. That's O of log n. Even with a million items, you need only about twenty checks.

Most modern languages also give us dynamic arrays, like lists in Python, ArrayList in Java, or vectors in C plus plus. I would argue that {{ argument_dynamic_array_tradeoff }}.

That weakness leads us directly to our second data structure: the linked list.

Return to the problem from before. We want to insert a new name at the beginning. With a linked list, we create a new node, point it at the current first node, and update the start of the list. Nobody else moves. That's O of one.

No, exactly. There are no locker numbers. I have to start at the first node and follow the links, five hundred times. Accessing by position is O of n. In a treasure hunt, you can't skip to clue number twenty without reading the first nineteen. Linked lists also use extra memory for all those links, and because nodes are scattered, they're often slower in practice than arrays.

The next two structures are less about how data is stored and more about the rules for using it: stacks and queues.

Time for another quick exercise: in the next thirty seconds, with your neighbor, try to name one feature you use every day that behaves like a stack.

Stacks and queues are ideas, or rules. You can build them using either arrays or linked lists underneath. That's what computer scientists call an abstract data type: we care about what operations it supports, not how it's built inside.

A hash table stores data as key-value pairs. The key could be a student ID, and the value that student's full record. The mechanism is easy to picture: a wall of one hundred mailboxes, numbered zero to ninety-nine. To store a record, we run its key through a special function called a hash function, which turns the key into a number, say, forty-two. The record goes in mailbox forty-two. Later, to find that student, we run the same key through the same function, get forty-two again, and go straight there. On average, that's O of one for searching, inserting, and deleting.

Exactly: at least two students will end up with the same mailbox number. This is called a collision, and it can happen long before the table is full, just by chance. One common fix is chaining: each mailbox holds a small list, so if two records land in the same place, we keep both. With a good hash function, and a table that grows when it gets too full, collisions stay rare and operations stay fast on average.

What are hash tables bad at? In my opinion, {{ argument_hash_table_limits }}.

I'm going to describe five real-world problems. For each one, discuss with the people around you and decide which data structure you would choose, and, more importantly, why. Think about which operations matter most in each case.

Problem two: a web server receives thousands of requests per second, and must process them fairly, in the order they arrived.

Problem four: a music player keeps a playlist where songs are constantly inserted and removed right next to the song that's currently playing.

Okay, let's bring it back together and check the answers.

Three takeaways to carry out of this room. Above all, I believe {{ argument_choosing_structures_by_operations }}.

{{ argument_hands_on_lab_instructions }}

You did the thinking today, and it showed. Before we move on, what's still unclear?
