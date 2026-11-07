---
topic: "Introduction to Data Structures Workshop"
category: "Technology"
duration_min: 33
---
Good {{ time_of_day }}, everyone, and welcome to {{ workshop_name }}. I'm {{ speaker_name }}, and for the next half hour or so, we're going to explore one of the most important foundations of computer science: data structures.

To set the scene: one hundred thousand books piled randomly on the floor. Or the same hundred thousand books, sorted on shelves, with a catalog at the entrance. Same books, but a very different afternoon if you need to find one. Keep those two libraries in mind, because they hold the whole idea of today's session.

A word on how this workshop will work. This is not a lecture where I talk and you listen. Every few minutes, I'll ask you a question or give you a small challenge to think about with the person next to you. There are no wrong answers in these moments. The goal is to get your brain working, because data structures are much easier to understand when you reason about them yourself, rather than just memorizing definitions.

The session has three parts. Part one asks why data structures matter at all. Part two goes through six essential structures: arrays, linked lists, stacks, queues, hash tables, and trees, with a short look at graphs at the end. For each one, we'll answer three questions: how does it organize data, what is it good at, and what is it bad at? Part three is a challenge where you'll choose the right data structure for real-world problems.

The big question first: why should we care?

Back to those two libraries, and one question: how long does it take to find a specific book? In the first, you might spend days. In the second, shelved by subject and then alphabetically by author, with a catalog at the entrance, you'll find it in a couple of minutes.

Notice something: both libraries contain exactly the same information. The difference is entirely in how that information is organized. And that is what a data structure is: a way of organizing data so that certain operations become efficient.

In programming, the operations we care about are usually things like: accessing an item, searching for an item, inserting a new item, and deleting an item. Different data structures make different operations fast, and others slow. There's no perfect structure that's best at everything. Choosing a data structure is always about trade-offs, and learning to see those trade-offs is the real skill we're building today.

To describe how fast an operation is, we'll use Big-O notation, but only in a very simple way. O of one means the operation takes the same time no matter how much data we have. That's the best case. O of n means the time grows in proportion to the amount of data: twice the data, twice the work. And O of log n means that the time grows very slowly, because we cut the problem in half at each step. That's all the theory you need for today.

Our first data structure is the array.

An array is a collection of items stored one after another, in a continuous block of memory. Picture a row of numbered lockers in a school hallway. Locker zero, locker one, locker two, and so on. Notice that in most programming languages, we start counting from zero.

Because all the lockers are the same size and sit next to each other, the computer can calculate exactly where any locker is. If you want locker number five hundred, the computer doesn't need to walk past the first four hundred and ninety-nine. It jumps straight there. Accessing an item by its index is therefore O of one. That's the array's superpower.

But arrays have a weakness, and our first quick exercise will find it.

Take a row of ten lockers, all full, holding names in alphabetical order. A new student arrives, and their name needs to go in position zero, at the very beginning, to keep the order. What has to happen to the other nine names? Take thirty seconds and discuss it with your neighbor.

All right, what did you come up with? Exactly. Every single item has to shift one position to the right to make room. With ten items, that's fine. With ten million items, that's ten million moves. Inserting or deleting at the beginning or in the middle of an array is O of n. It's slow for large data.

Searching is another thing to think about. If the array isn't sorted, and you want to know whether the name "Linh" is in there, you have to check each locker one by one. That's O of n. But if the array is sorted, you can use binary search: open the middle locker, decide whether your name comes before or after it, and throw away half of the lockers each time. That's O of log n, which is dramatically faster. Even with a million items, you need only about twenty checks.

One more thing. Classic arrays have a fixed size: you decide how many lockers you need when you build them. But most modern languages give us dynamic arrays, like lists in Python, ArrayList in Java, or vectors in C plus plus. They grow automatically. When they run out of space, they quietly create a bigger array, usually about double the size, and copy everything over. Copying is expensive, but because it happens rarely, adding to the end of a dynamic array is still fast on average.

Arrays, in one line: excellent for fast access by position and for storing data compactly, but slow for inserting and deleting in the middle.

That weakness leads us directly to our second data structure: the linked list.

A linked list solves the insertion problem in a clever way. Instead of storing items side by side, each item, which we call a node, stores two things: its data, and a pointer, or link, to the next node. The nodes can live anywhere in memory. They're connected only by these links.

A treasure hunt is a good way to picture a linked list. Each clue tells you something, and also tells you where to find the next clue. You don't need all the clues to be in the same room. You just follow the chain.

Return to the problem from before. We want to insert a new name at the beginning. With a linked list, we create a new node, point it at the current first node, and update the start of the list to point at our new node. That's it. Nobody else moves. That's O of one. Similarly, if we're already standing at a certain position in the list, inserting or removing the next node only requires changing a couple of links.

Quick question for everyone, and just shout out the answer: if I want the five hundredth item in a linked list, can I jump straight to it like an array?

No, exactly. There are no locker numbers. I have to start at the first node and follow the links, one by one, five hundred times. Accessing by position is O of n. In a treasure hunt, you can't skip to clue number twenty without reading the first nineteen.

Linked lists also use extra memory for all those links, and because nodes are scattered around memory, they're often slower in practice than arrays, since modern computers are much faster at reading memory that sits close together.

There's also a variation called a doubly linked list, where each node links to both the next and the previous node, so you can move in both directions. Browser history and music playlists can work this way.

That gives us our first big trade-off. Arrays: fast access, slow insertion. Linked lists: fast insertion, slow access. Keep that contrast in mind, because it's the pattern you'll see again and again.

The next two structures are less about how data is stored and more about the rules for using it. These are stacks and queues.

A stack follows one simple rule: last in, first out. A stack of plates in a cafeteria works the same way. You put a new plate on top, and when you need one, you take it from the top. You never pull a plate out from the middle or the bottom.

A stack has two main operations. Push adds an item to the top. Pop removes the item from the top. Both are O of one.

Stacks are everywhere in computing. Time for another quick exercise: in the next thirty seconds, with your neighbor, try to name one feature you use every day that behaves like a stack.

Great, who wants to share? Yes, the undo button is a perfect example. Every action you take is pushed onto a stack, and when you press undo, the most recent action is popped off and reversed. The back button in your browser is another one. And, behind the scenes, when a program calls functions inside other functions, the computer keeps track of them using a call stack. If you've ever seen the famous "stack overflow" error, that's what happened: the call stack ran out of space, usually because of a recursion that never stopped.

A queue is the opposite: first in, first out. It's exactly like a line at a coffee shop. The first person to arrive is the first person to be served. New people join at the back, and people leave from the front.

The two main operations are enqueue, which adds an item to the back, and dequeue, which removes an item from the front. Done correctly, both are O of one.

Queues appear whenever we need fairness, or need to process things in the order they arrived. Documents waiting to be printed. Messages waiting to be processed by a server. Customers waiting in an online ticket system. And, as we'll see later, queues are also the key tool for exploring maps and networks level by level.

One subtlety is worth knowing: stacks and queues are ideas, or rules. You can build them using either arrays or linked lists underneath. That's a great example of what computer scientists call an abstract data type: we care about what operations it supports, not how it's built inside.

Every structure we've seen so far shares the same problem with searching: to find a specific item, we usually have to look through many items. What if we could find anything almost instantly? That brings us to what is probably the most useful data structure in everyday programming: the hash table.

A hash table stores data as key-value pairs. The key is what you look up by, and the value is the information you want. The key could be a student ID, and the value could be that student's full record. Or the key could be a word, and the value its definition.

The mechanism is easy to picture: a wall of one hundred mailboxes, numbered zero to ninety-nine. When we want to store a student's record, we take their key, the student ID, and run it through a special function called a hash function. The hash function turns the key into a number, say, forty-two. The record goes in mailbox forty-two.

Later, when we want to find that student, we don't search through the mailboxes. We run the same key through the same hash function, get forty-two again, and go straight to that mailbox. On average, that's O of one for searching, inserting, and deleting, no matter how many records we store.

There's a catch, though, and one more thinking exercise will expose it. We have one hundred mailboxes, and we want to store records for one hundred and fifty students. What problem is guaranteed to happen? Take thirty seconds.

Exactly: at least two students will end up with the same mailbox number. This is called a collision. And actually, collisions can happen long before the table is full, just by chance.

There are two common ways to handle collisions. The first is chaining: each mailbox can hold a small list of items, so if two records land in the same mailbox, we just keep both and check that short list. The second is open addressing: if the mailbox is full, we look for the next empty one according to a fixed rule. In both cases, a good hash function spreads keys evenly, and the table grows when it gets too full, so collisions stay rare and operations stay fast on average.

What are hash tables bad at? They don't keep items in any meaningful order. If you need your data sorted, or you need to find all students with IDs between one thousand and two thousand, a hash table won't help you much.

You've almost certainly used hash tables already, even if you didn't know it. In Python they're called dictionaries and sets. In Java, HashMap and HashSet. In JavaScript, objects and Map. They're used for caches, for counting how often words appear, for checking whether you've already seen something, and for database indexes. If there's one data structure you'll reach for most often in real programming, it's probably this one.

The next structure represents something every one of you has seen on your computer: the tree.

All our structures until now have been linear: one item after another. But a lot of real-world data is hierarchical. Look at the folders on your computer: a folder contains files and other folders, which contain more files and folders. Or at a company's organization chart, or a family tree. This kind of data is naturally represented by a tree.

A tree is made of nodes connected by edges. At the very top, there's a single node called the root. Each node can have children, and nodes without children are called leaves. Yes, computer scientists draw trees upside down, with the root at the top and leaves at the bottom. Don't ask me why.

One especially useful type is the binary search tree. In a binary tree, each node has at most two children: a left child and a right child. And in a binary search tree, we add one rule: everything in the left subtree is smaller than the node, and everything in the right subtree is larger.

Why is that rule so powerful? Suppose the root is fifty, and we're looking for thirty-seven. Is thirty-seven smaller or larger than fifty? Smaller, so we go left, and we can completely ignore everything on the right side. Maybe the next node is twenty-five. Is thirty-seven smaller or larger? Larger, so we go right. At every step, we eliminate about half of the remaining tree. Does that remind you of anything we've seen today?

Yes, it's the same idea as binary search on a sorted array. Searching takes O of log n. But unlike a sorted array, inserting a new value doesn't require shifting everything: we just walk down the tree and attach the new node in the right place, also in O of log n. And because of the left-smaller, right-larger rule, the tree keeps everything in sorted order, so it's great for range questions, like "give me all values between thirty and sixty," which hash tables can't do well.

But there's a trap. What happens if we insert the numbers one, two, three, four, five, in that order, into an empty binary search tree? Each new number is larger than the last, so each one goes to the right. We end up with a long, thin chain, which is basically a linked list. And searching becomes O of n again.

To prevent this, real systems use self-balancing trees, such as AVL trees and red-black trees, which automatically reorganize themselves to stay short and wide. You don't need to know how they work today. Just know that they exist, and that when a language or library offers a sorted map or sorted set, there's usually a balanced tree behind it. A close relative, called the B-tree, is used inside almost every database to make searching through millions of records fast.

One more structure deserves a brief mention before the final challenge: the graph.

A tree is actually a special kind of graph. In a general graph, any node can connect to any other node, and there's no single root. Graphs model networks: cities connected by roads, people connected by friendships on a social network, web pages connected by links.

Whenever a map app finds the fastest route from your home to the university, it's searching a graph. Whenever a social network suggests "people you may know," it's exploring a graph, often using a queue to look at your friends first, then friends of friends, and so on. Graphs deserve a full workshop of their own, so for today, just remember: when your data is about relationships and connections, think graph.

All right. Time to put everything together. This is the main exercise of today's workshop.

I'm going to describe five real-world problems. For each one, discuss with the people around you and decide which data structure you would choose, and, more importantly, why. Think about which operations matter most in each case. You'll have about five minutes for all five. Ready?

Problem one: a text editor needs an undo feature.

Problem two: a web server receives thousands of requests per second, and must process them fairly, in the order they arrived.

Problem three: a login system needs to check, very quickly, whether a username already exists, among ten million users.

Problem four: an online leaderboard must keep players sorted by score at all times, and frequently answer questions like "who is ranked between one hundred and two hundred?"

Problem five: a game stores the scores of exactly twelve players, and frequently needs to read the score of player number seven.

Your five minutes start now.

Okay, let's bring it back together and check the answers.

Problem one, undo: a stack. The most recent action is always the first one to be undone. Last in, first out.

Problem two, processing requests fairly: a queue. First come, first served.

Problem three, checking whether a username exists: a hash table, or more specifically a hash set. We don't care about order. We just need near-instant lookups, and a hash table gives us O of one on average, even with ten million users.

Problem four, the leaderboard: a balanced binary search tree, or a similar sorted structure. We need the data sorted at all times, and we need range questions, which hash tables don't handle well. Insertions and updates stay at O of log n.

And problem five, twelve players accessed by number: a simple array. The size is small and fixed, and we need direct access by position. Sometimes the simplest structure is the best one. Don't use a complicated tool when a simple one does the job.

How did you do? If you got most of these, congratulations. You're already thinking like a software engineer. And if some of them surprised you, that's perfectly normal. This kind of judgment grows with practice.

Four takeaways to carry out of this room.

First, a data structure is a way of organizing data so that certain operations become efficient. Same data, different organization, completely different performance.

Second, there is no perfect data structure. Each one is a set of trade-offs. Arrays give fast access but slow insertion in the middle. Linked lists give fast insertion but slow access. Stacks give you last in, first out. Queues give you first in, first out. Hash tables give near-instant lookups but no order. Trees keep data sorted with fast search, as long as they stay balanced. And graphs represent relationships.

Third, the right question is never "which data structure is the best?" It's always "which operations does my problem need most, and which structure makes those operations fast?"

And finally, most of the time, you won't build these structures from scratch. Your programming language already provides excellent versions of them. But understanding how they work inside is exactly what allows you to choose the right one, and to understand why your program is fast, or why it suddenly becomes slow when the data grows.

{{ hands_on_lab_instructions }}

You did the thinking today, and it showed. Before we move on, what's still unclear?
