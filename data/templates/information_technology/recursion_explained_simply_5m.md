---
topic: "Recursion Explained Simply"
category: "Technology"
duration_min: 5
---
Stand between two mirrors, and you'll see your reflection repeated again and again, each copy a little smaller than the last. Hold on to that picture, because it's the easiest way into today's topic.

Hi everyone, I'm {{ argument_speaker_name }}, and we're going to tackle something that confuses almost everyone the first time they meet it: recursion. That mirror effect is exactly its spirit: something defined in terms of a smaller version of itself. By the end of these few minutes, I want recursion to feel less like a puzzle and more like a tool you can actually use.

In programming, recursion simply means a function that calls itself. That's it. But a function that calls itself forever would never stop, so every recursive function needs two essential parts.

The first part is the base case. This is the simplest version of the problem, the one we can answer directly without any more calls. It's the stopping point.

The second part is the recursive case. This is where the function breaks the problem into a smaller piece of the same problem and calls itself on that smaller piece.

The classic place to see it is factorial. The factorial of five, written five with an exclamation mark, is five times four times three times two times one, which equals one hundred and twenty.

Now look at it a little differently. Five factorial is just five times four factorial. And four factorial is four times three factorial. Do you see the pattern? Each problem contains a smaller copy of itself. That lets us write it like this: the factorial of n equals n times the factorial of n minus one. That's our recursive case. And the factorial of one is just one. That's our base case.

When the computer runs factorial of five, it pauses at each step and asks about the smaller number: four, then three, then two, then one. At one, it finally hits the base case. Then it works its way back up: two, six, twenty-four, and finally one hundred and twenty.

The computer keeps track of all these paused calls on something called the call stack, which explains a famous error you might see: "stack overflow." It happens when there are so many calls, usually because the base case is missing or never reached, that the stack runs out of space.

For factorial, a simple loop works just as well. But some problems are naturally recursive. Their structure is made of smaller copies of themselves. The folders on your computer are a perfect case. A folder can contain files, and also other folders, which contain more folders. If you want to find every file inside, recursion is the most natural way to do it: handle the files here, then do the same thing for each sub-folder.

Recursion isn't free, though. Each call uses memory on the stack, so very deep recursion can be slow or even crash. And a careless recursive solution can repeat the same work many times. The Fibonacci sequence is a well-known trap: a naive recursive version recalculates the same values over and over. The fix is a technique called memoization, which simply means remembering answers you've already computed.

How, then, should you approach a recursive problem? A three-step recipe helps. Begin by identifying the smallest case you can solve directly: that's your base case. Then assume your function already works for a slightly smaller input. This is the leap of faith, and it's the hardest part for beginners. Finally, use that smaller answer to build the answer for the current input.

A challenge to take home: {{ argument_practice_exercise }} Try to identify the base case first, then the recursive case.

To wrap up: recursion is a function calling itself on a smaller version of the problem. It always needs a base case to stop and a recursive case that moves toward it. It shines when a problem has a self-similar structure, like folders inside folders, and it should be used with care when the recursion can go very deep.

Over to you: what's still unclear?
