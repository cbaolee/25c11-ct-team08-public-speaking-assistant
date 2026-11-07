---
topic: "Will AI Replace Programmers"
category: "Technology"
duration_min: 21
---
"Will AI replace programmers?" People ask that question constantly: students, parents, junior developers, and sometimes very senior engineers. Good {{ time_of_day }}, everyone. I'm {{ speaker_name }}, and {{ speaker_background }} Today, I'd like to answer it directly.

It's a fair question. In just a few years, we've gone from AI tools that could autocomplete a line of code, to tools that can write entire functions, explain unfamiliar codebases, fix bugs, and complete multi-step programming tasks with limited supervision. If you're a student who just spent a weekend debugging an assignment, and you see an AI produce similar code in seconds, it's natural to wonder: what's the point?

My position, from the start: I don't believe AI will replace programmers as a profession in the foreseeable future. But I do believe it's already changing what programmers do, which skills matter most, and how people enter the profession. And some people who refuse to adapt will find their work much less valuable. So the answer is neither "don't worry" nor "panic." It's "pay attention, and adapt."

The reasons follow, with arguments on both sides, because you deserve a fair picture, not just an opinion.

Let's start with the case that AI will replace programmers, and let's take it seriously.

Argument one: the capabilities are improving very fast. Tasks that AI tools couldn't do reliably a few years ago, like implementing a feature across several files, or fixing a bug from an issue description, are now often within reach for well-specified problems. If that pace continues, it's reasonable to ask where it ends.

Argument two: much programming work is routine. A lot of professional code consists of familiar patterns: forms, database queries, API endpoints, tests, and integrations. These are exactly the kinds of tasks that AI tools handle best, because they've seen countless similar examples.

And argument three: economics. If a company can get the same software with fewer people, there's strong pressure to do so. Some company leaders have publicly said that AI is reducing their need to hire for certain roles.

These arguments are real, and I don't want to dismiss them.

Now, let's look at the other side.

Argument one: writing code was never the whole job. Studies of how developers spend their time consistently find that writing new code is only part of it. The rest is understanding requirements, reading existing code, designing systems, reviewing others' work, debugging, testing, communicating with colleagues and customers, and making trade-offs. AI helps with parts of these, but the hardest parts are about understanding what's actually needed, in a messy, specific, human context.

Let me give you an example. A client asks for "a simple booking system." What does "simple" mean? Should customers be able to cancel? Until when? What happens if two people book the same slot at the same time? What if the payment succeeds but the confirmation email fails? What about customers who don't have a smartphone? None of these questions are about syntax. They're about understanding a business, its users, and what can go wrong. An AI can help you list such questions. But someone still has to ask the client, make decisions, and take responsibility for them.

Argument two: someone has to be responsible. When software handles money, health data, or safety-critical systems, someone must understand what it does, verify that it's correct, and be accountable when it fails. AI tools can produce code that looks correct but contains subtle bugs or security vulnerabilities. The more code AI produces, the more important it becomes to have skilled people who can review it, test it, and understand it deeply.

Argument three: we've seen this pattern before. The history of programming is a history of automation. Assembly language automated machine code. Compilers and high-level languages automated much of assembly. Frameworks, libraries, and cloud services automated huge amounts of work that developers used to do by hand. Each time, people predicted that fewer programmers would be needed. And each time, software became cheaper to build, so people wanted much more of it, and the demand for developers grew. Economists call this kind of effect the Jevons paradox: when something becomes more efficient to produce, total demand for it can increase. Whether this pattern will repeat with AI isn't guaranteed, but it's a serious counter-argument.

There's a well-known example outside programming, too. When electronic spreadsheets appeared around 1980, starting with VisiCalc, they automated an enormous amount of manual calculation that bookkeepers and clerks used to do by hand. Many of those clerical jobs did decline over the following decades. But the number of people doing financial analysis grew, because once calculations became cheap, businesses wanted many more of them: more scenarios, more forecasts, more models. The work didn't disappear. It moved up a level, from calculating to analyzing and deciding. Notice, though, that this shift wasn't painless for everyone. The people whose work was only calculation had to adapt or move on. That's an important part of the lesson for us, too.

And argument four: the remaining problems are hard. Today's AI tools perform best on well-defined tasks with clear success criteria. They tend to struggle more with large, unfamiliar systems, ambiguous requirements, novel problems, and long tasks where small mistakes compound. These are exactly the situations where experienced engineers spend most of their effort.

To make this less abstract, in practical terms: where today's AI coding tools tend to be strong, and where they tend to struggle. This is based on how these tools behave in day-to-day use, and it will keep changing, but the pattern has been fairly consistent.

They're usually strong at: writing small, self-contained functions with a clear description; producing boilerplate, like configuration files, data models, and simple endpoints; translating code from one language or framework to another; explaining what an unfamiliar piece of code does; writing a first draft of tests; and suggesting fixes for common error messages.

They tend to struggle more with: understanding the unwritten rules of a large, specific codebase, such as why a certain workaround exists; requirements that are ambiguous or contradictory; performance and concurrency problems that only appear under real load; security, where code that works can still be dangerous; and knowing when they don't know. An AI tool will often produce a confident, plausible answer even when it's wrong, which means the person using it has to be able to tell the difference.

Notice the pattern. The strengths are about producing code. The weaknesses are about judgment and context. That's an important clue about where human value is moving.

So, where does this leave us? An assessment.

First, the job is shifting, not disappearing. Less time typing routine code, more time on specifying problems precisely, designing systems, reviewing and testing, and integrating AI into products. A useful way to think about it: developers are moving from being only writers of code, to being writers, reviewers, and directors of code, some of which is produced by AI.

Second, the entry point is the biggest concern. This is the part that worries me most. Junior developers have traditionally learned by doing exactly the kind of routine tasks that AI now handles well. If companies hire fewer juniors because AI does that work, how will the next generation of seniors be trained? There are early signs that entry-level hiring has become harder in parts of the industry, although it's difficult to separate the effect of AI from other factors, such as economic conditions and the end of the very high hiring levels of a few years ago. Either way, it means that if you're a student today, you need to be more deliberate about building real skills, not less.

Third, the value of shallow knowledge is falling, and the value of deep knowledge is rising. If your only skill is translating clear instructions into code in one framework, AI can increasingly do that. But if you understand how systems work, why they fail, how to design them, and how to judge whether a solution is correct, AI makes you more productive, not less needed.

And fourth, new kinds of work are appearing. Every major wave of automation has created jobs that didn't exist before, and we can already see some of them. Companies building products with AI need engineers who can connect language models to real data and systems safely, design evaluations that measure whether an AI feature actually works, monitor AI systems in production for errors, cost, and drift, and protect them against new kinds of attacks, such as prompt injection. There's also growing demand for people who combine software skills with deep knowledge of a specific field, because applying AI well in medicine, law, finance, or education requires understanding those fields. Many of these roles are still being defined, and their names will probably change several times. But they all have one thing in common: they require strong software engineering fundamentals, plus an understanding of how AI systems behave and fail.

So when people ask whether there will be jobs for programmers in ten years, the answer is: almost certainly yes, but many of them will look different from today's, in the same way that today's jobs look very different from those of twenty years ago, when cloud computing and smartphones barely existed.

{{ speaker_personal_observation }}

A story of two developers illustrates the point. It's a composite example.

Two junior developers are given the same task: add a feature that lets users export their order history as a file. Both use an AI assistant.

The first developer types the task into the AI, gets a block of code, pastes it in, sees that the export works on their test account, and opens a pull request. In review, a senior engineer asks a few questions. What happens if a user has fifty thousand orders? The code loads all of them into memory at once, which could crash the server. Can a user export someone else's orders by changing the ID in the request? Yes, because the code doesn't check permissions. And are dates exported in the user's time zone? No. The developer can't answer these questions, because they don't fully understand the code they submitted.

The second developer starts differently. Before asking the AI anything, they spend twenty minutes thinking about the problem: How large can the data get? Who's allowed to export what? What format do users actually need? Then they use the AI to draft the code quickly, but they read every line, ask the AI to explain the parts they're unsure about, add a permission check, process the data in batches, and write tests for the edge cases they identified. Their pull request takes a bit longer, but it's approved with minor comments.

Both used AI. Both were fast. But only one of them was doing the actual job of a software engineer. And as AI tools improve, the gap between these two developers won't shrink. It will grow, because the first one is learning nothing, and the second one is learning faster than ever.

So, what should you actually do? It depends on where you are.

If you're a student:

First, learn the fundamentals deeply. Data structures, algorithms, operating systems, networks, databases, and security. These are what let you understand, evaluate, and fix code, whether a person or an AI wrote it.

Second, use AI as a tutor, not as a ghostwriter. When you're stuck, ask it to explain a concept, give you a hint, or review your code. But write the solution yourself. If AI completes your assignments, you'll graduate with a degree but without the skills, and that gap will show very quickly in interviews and on the job.

Third, build real projects, end to end. Choose problems that matter to someone, deal with messy requirements, deploy them, and maintain them. That's where you learn the parts of the job that AI can't do for you.

If you're already a developer:

First, learn to use AI tools well. That's now a professional skill, like using version control. Learn what they're good at, where they fail, and how to verify their output.

Second, strengthen the skills that become more valuable: system design, code review, testing, security, and debugging complex problems.

Third, get closer to the problem. Understand your users, your business domain, and why you're building what you're building. Developers who understand the domain, whether it's healthcare, finance, logistics, or education, are much harder to replace than those who only understand the code.

And fourth, develop your communication skills. Explaining trade-offs, writing clear specifications, and working with non-technical people will matter even more when AI handles more of the typing.

And for everyone: stay curious and keep learning. The tools will keep changing. Your ability to learn new ones, quickly and critically, is the most durable skill you have.

Before I finish, three questions that come up often on this topic.

First: "But won't AI eventually be able to do everything, including the judgment parts?" Nobody knows for sure, and I'd be suspicious of anyone who claims certainty either way. AI capabilities may continue improving in ways that surprise us. But even in very optimistic scenarios, the transition would likely be gradual, and the people best positioned to adapt would be those who understand both technology and the problems it's used to solve. Building that understanding is a good bet in almost every future.

Second: "Is it still worth studying computer science?" I believe yes, but the reasons are shifting. It's less about learning to type code in a particular language, and more about learning to think computationally, understand systems, and solve problems rigorously. Those abilities are valuable in software engineering, and also in data, security, product, research, and many other fields where technology meets real problems.

And third: "Should I worry about my job?" If your job consists only of tasks that are routine, well-specified, and easy to verify, it's wise to start expanding your skills now. Not out of fear, but because it will make your work more interesting and more valuable anyway. If your job involves understanding problems, designing solutions, and taking responsibility for quality, AI is far more likely to be a powerful assistant than a replacement.

One last thought. Every major technology in the history of programming has raised the same fear, and each time, the people who did best weren't those who resisted the new tool, or those who blindly trusted it. They were those who understood it, used it wisely, and focused on the problems that still required human judgment.

AI is the most powerful tool programmers have ever had. But a tool doesn't decide what's worth building, who it's for, what could go wrong, or whether it's good enough to trust with people's money, health, or safety. That's still our job. And I believe it will be for a long time.

So the real question isn't "Will AI replace programmers?" It's "What kind of programmer do you want to become, now that AI exists?" My hope is that you'll choose to become the kind that AI makes stronger.

I'd love to hear your questions, and your own views. I'm sure not everyone here agrees with me, and that's exactly what makes this a good conversation.
