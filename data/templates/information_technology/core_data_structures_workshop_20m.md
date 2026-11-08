---
topic: "Core Data Structures Workshop: Arrays, Lists, Stacks, Queues and Hash Tables"
Category: "Information Technology"
duration_min: 20
---
Good {{ argument_time_of_day }}, everyone, and welcome to {{ argument_workshop_name }}. I'm {{ argument_speaker_name }}, and for the next twenty minutes, we're going to explore the core data structures that almost every program relies on: arrays, linked lists, stacks, queues, and hash tables.

To set the scene: one hundred thousand books piled randomly on the floor. Or the same hundred thousand books, sorted on shelves, with a catalog at the entrance. Same books, but a very different afternoon if you need to find one. Keep those two libraries in mind, because they hold the whole idea of today's session.

A word on how this workshop will work. This is not a lecture where I talk and you listen. Every few minutes, I'll give you a small challenge to think about with the person next to you. There are no wrong answers in these moments. Data structures are much easier to understand when you reason about them yourself, rather than just memorizing definitions.

Why do data structures matter at all? Go back to those two libraries. Both contain exactly the same information. The difference is entirely in how that information is organized. And that is what a data structure is: a way of organizing data so that certain operations become efficient.

In programming, the operations we care about are usually accessing an item, searching for an item, inserting a new item, and deleting an item. Different data structures make different operations fast, and others slow. There's no perfect structure that's best at everything. Choosing one is always about trade-offs, and learning to see those trade-offs is the real skill we're building today.

To describe speed, we'll use Big-O notation in a very simple way. O of one means the operation takes the same time no matter how much data we have. O of n means the time grows in proportion to the data: twice the data, twice the work. And O of log n means the time grows very slowly, because we cut the problem in half at each step. That's all the theory you need for today.

Our first data structure is the array.

An array is a collection of items stored one after another, in a continuous block of memory. Picture a row of numbered lockers in a school hallway. Locker zero, locker one, locker two, and so on. Because all the lockers are the same size and sit next to each other, the computer can calculate exactly where any locker is. If you want locker number five hundred, it doesn't need to walk past the first four hundred and ninety-nine. It jumps straight there. Accessing an item by its index is therefore O of one. That's the array's superpower.

But arrays have a weakness, and our first quick exercise will find it.

Take a row of ten lockers, all full, holding names in alphabetical order. A new student arrives, and their name needs to go in position zero, at the very beginning, to keep the order. What has to happen to the other nine names? Take thirty seconds and discuss it with your neighbor.

[Pair discussion, about thirty seconds.]

All right, what did you come up with? Exactly. Every single item has to shift one position to the right to make room. With ten items, that's fine. With ten million items, that's ten million moves. Inserting or deleting at the beginning or in the middle of an array is O of n.

Searching is another thing to think about. If the array isn't sorted, you have to check each locker one by one: O of n. But if it's sorted, you can use binary search: open the middle locker, decide whether your name comes before or after it, and throw away half of the lockers each time. That's O of log n. Even with a million items, you need only about twenty checks.

Most modern languages also give us dynamic arrays, like lists in Python, ArrayList in Java, or vectors in C plus plus. When they run out of space, they quietly create a bigger array, usually about double the size, and copy everything over. Because that happens rarely, adding to the end is still fast on average.

Arrays, in one line: excellent for fast access by position, but slow for inserting and deleting in the middle.

That weakness leads us directly to our second data structure: the linked list.

Instead of storing items side by side, each item in a linked list, called a node, stores two things: its data, and a link to the next node. The nodes can live anywhere in memory. A treasure hunt is a good way to picture it: each clue tells you something, and also tells you where to find the next clue.

Return to the problem from before. We want to insert a new name at the beginning. With a linked list, we create a new node, point it at the current first node, and update the start of the list. Nobody else moves. That's O of one.

Quick question for everyone, and just shout out the answer: if I want the five hundredth item in a linked list, can I jump straight to it like an array?

No, exactly. There are no locker numbers. I have to start at the first node and follow the links, five hundred times. Accessing by position is O of n. In a treasure hunt, you can't skip to clue number twenty without reading the first nineteen. Linked lists also use extra memory for all those links, and because nodes are scattered, they're often slower in practice than arrays.

That gives us our first big trade-off. Arrays: fast access, slow insertion. Linked lists: fast insertion, slow access. Keep that contrast in mind, because it's a pattern you'll see again and again.

The next two structures are less about how data is stored and more about the rules for using it: stacks and queues.

A stack follows one simple rule: last in, first out. A stack of plates in a cafeteria works the same way. You put a new plate on top, and you take one from the top. Push adds an item to the top, and pop removes it. Both are O of one.

Time for another quick exercise: in the next thirty seconds, with your neighbor, try to name one feature you use every day that behaves like a stack.

[Pair discussion, about thirty seconds.]

Great, who wants to share? Yes, the undo button is a perfect example. Every action you take is pushed onto a stack, and when you press undo, the most recent action is popped off and reversed. The back button in your browser is another one. And when a program calls functions inside other functions, the computer keeps track of them using a call stack. If you've ever seen a "stack overflow" error, that's what happened: the call stack ran out of space.

A queue is the opposite: first in, first out, exactly like a line at a coffee shop. New people join at the back, and people leave from the front. Enqueue adds an item to the back, and dequeue removes one from the front, both in O of one. Queues appear whenever we need fairness, or need to process things in the order they arrived: documents waiting to be printed, messages waiting for a server, customers waiting in an online ticket system.

Stacks and queues are ideas, or rules. You can build them using either arrays or linked lists underneath. That's what computer scientists call an abstract data type: we care about what operations it supports, not how it's built inside.

Every structure we've seen so far shares the same problem with searching: to find a specific item, we usually have to look through many items. What if we could find anything almost instantly? That brings us to what is probably the most useful data structure in everyday programming: the hash table.

A hash table stores data as key-value pairs. The key could be a student ID, and the value that student's full record. The mechanism is easy to picture: a wall of one hundred mailboxes, numbered zero to ninety-nine. To store a record, we run its key through a special function called a hash function, which turns the key into a number, say, forty-two. The record goes in mailbox forty-two. Later, to find that student, we run the same key through the same function, get forty-two again, and go straight there. On average, that's O of one for searching, inserting, and deleting.

There's a catch, though, and one more thinking exercise will expose it. We have one hundred mailboxes, and we want to store records for one hundred and fifty students. What problem is guaranteed to happen? Take thirty seconds.

[Pair discussion, about thirty seconds.]

Exactly: at least two students will end up with the same mailbox number. This is called a collision, and it can happen long before the table is full, just by chance. One common fix is chaining: each mailbox holds a small list, so if two records land in the same place, we keep both. With a good hash function, and a table that grows when it gets too full, collisions stay rare and operations stay fast on average.

What are hash tables bad at? They don't keep items in any meaningful order. If you need your data sorted, a hash table won't help you much. But you've almost certainly used them already: in Python they're called dictionaries and sets, in Java HashMap and HashSet, and in JavaScript objects and Map.

All right. Time to put everything together. This is the main exercise of today's workshop.

I'm going to describe five real-world problems. For each one, discuss with the people around you and decide which data structure you would choose, and, more importantly, why. Think about which operations matter most in each case.

Problem one: a text editor needs an undo feature.

Problem two: a web server receives thousands of requests per second, and must process them fairly, in the order they arrived.

Problem three: a login system needs to check, very quickly, whether a username already exists, among ten million users.

Problem four: a music player keeps a playlist where songs are constantly inserted and removed right next to the song that's currently playing.

Problem five: a game stores the scores of exactly twelve players, and frequently needs to read the score of player number seven.

[Group exercise, about four minutes.]

Okay, let's bring it back together and check the answers.

Problem one, undo: a stack. The most recent action is always the first one to be undone.

Problem two, processing requests fairly: a queue. First come, first served.

Problem three, checking whether a username exists: a hash table, or more specifically a hash set. We don't care about order. We just need near-instant lookups, even with ten million users.

Problem four, the playlist: a linked list, ideally a doubly linked one, where each song links to both the next and the previous song. We're already standing at the current song, so inserting or removing its neighbors only means changing a couple of links. Nothing else has to shift.

And problem five, twelve players accessed by number: a simple array. The size is small and fixed, and we need direct access by position. Sometimes the simplest structure is the best one.

How did you do? If you got most of these, congratulations. You're already thinking like a software engineer. And if some of them surprised you, that's perfectly normal. This kind of judgment grows with practice.

Three takeaways to carry out of this room. First, a data structure is a way of organizing data so that certain operations become efficient. Second, there's no perfect structure, only trade-offs: arrays for fast access, linked lists for fast insertion, stacks for last in first out, queues for first in first out, and hash tables for near-instant lookups without order. And third, the right question is never "which data structure is the best?" It's "which operations does my problem need most, and which structure makes them fast?"

{{ argument_hands_on_lab_instructions }}

You did the thinking today, and it showed. Before we move on, what's still unclear?
