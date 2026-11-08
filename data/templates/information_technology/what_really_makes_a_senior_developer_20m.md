---
topic: "What Really Makes a Senior Developer"
category: "Technology"
duration_min: 20
---
Here's a question that sounds simple: what's the difference between a developer with five years of experience and a senior developer? If your answer is "about five years," I hope this talk changes your mind. I'm {{ argument_speaker_name }}, and {{ argument_speaker_background }}

Let me begin with a confession. {{ argument_speaker_junior_story }}

I share that story because many juniors assume that being senior means knowing more technologies and writing code faster. It takes some people years to see that the difference is much deeper than that. So in this talk, I'd like to save you some of those years.

The plan is simple: what "senior" really means, the six dimensions in which developers grow, a concrete story that shows those dimensions at work, and a short exercise to help you decide where to grow next.

What does "senior" actually mean?

Many people think it's about years of experience. But you've probably met people with ten years of experience who still work like juniors, and people with four years who are clearly senior. As the saying goes, some people have ten years of experience, and some people have one year of experience repeated ten times.

Others think senior means knowing many technologies. But a long list of frameworks on a CV doesn't make someone senior either.

In the career frameworks of many technology companies, seniority is mainly about three things: scope, autonomy, and impact.

Scope means the size and complexity of the problems you can handle. A junior developer usually works on well-defined tasks: "Add this field to this form." A mid-level developer can take a feature from start to finish: "Build the password reset flow." A senior developer can take a vague, complex problem and turn it into a clear plan: "Our checkout is too slow and customers are leaving. Figure out why, and fix it."

Autonomy means how much guidance you need. Juniors need regular guidance, and that's completely normal. Seniors can work independently, make sound decisions, and know when to ask for input.

And impact means how much your work affects the team and the business. A junior's impact is mostly through their own code. A senior's impact includes making the whole team better: through design decisions, code reviews, mentoring, and improving how the team works.

So when people ask, "How do I become senior?", the answer is: grow your scope, your autonomy, and your impact. Years of experience help only if you use them to grow in those three directions.

That growth happens along six dimensions.

Dimension one: technical depth. At the junior level, the focus is on making things work. When something breaks, a junior may try changes somewhat randomly until it works, and that's okay; everyone starts there. At the senior level, the focus shifts from "does it work?" to "why does it work, and will it keep working?" Senior developers understand the fundamentals underneath their tools: how the database executes a query, how concurrency works, how the network behaves. You see it most clearly in debugging. Instead of guessing, they form a hypothesis, gather evidence from logs, metrics, or a debugger, narrow down the problem step by step, and confirm the cause before fixing it.

A concrete example: imagine a page in your application suddenly becomes very slow. A junior might add caching everywhere, hoping something helps. A senior would first measure: which part is slow? They might discover that a database query is being executed hundreds of times in a loop, and fix it with one change that makes the page ten times faster. Same tools, very different approach.

Dimension two: system thinking and design. Juniors think mostly about the piece of code in front of them. Seniors think about the whole system. How does this change affect other parts? What happens when there are ten times more users? What happens when an external service is down, or the same request arrives twice? Most importantly, seniors think in trade-offs: faster to build versus easier to maintain, more flexible versus simpler. And here's something that surprises many juniors: senior developers often choose the simpler solution, because they've seen how complexity becomes expensive over time.

Dimension three: ownership and delivery. For a junior, responsibility often ends when the pull request is approved. A senior cares whether the feature actually works in production and whether it solved the problem. When things change, they communicate early. Picture a junior and a senior who both realize, halfway through a task, that it's much bigger than expected. The junior keeps working quietly, hoping to catch up, and misses the deadline. The senior goes to the team lead and says: "This is bigger than we thought, for this specific reason. We can deliver a smaller version by Friday, or the full version next Wednesday. What matters more?" That conversation, early and with options, is ownership.

Dimension four: communication. This is the dimension many developers underestimate the most, and often the one that makes the biggest difference in promotions. Senior developers write clearly: design documents, pull request descriptions, and bug reports that others can actually understand. They explain technical ideas to non-technical people in terms of impact: "If we don't fix this, checkout will fail during the next big sale." And they know how to disagree respectfully, with evidence, and then commit to the team's decision.

Dimension five: multiplying others. At the junior level, your main job is to grow yourself, and that's exactly right. At the senior level, an important part of your value comes from making others better: thoughtful code reviews that teach, mentoring, documentation that saves everyone time. There's a well-known idea that a senior engineer is a "force multiplier." If you make five teammates each ten percent more effective, your impact is bigger than if you simply wrote more code yourself. And being the "hero" who is the only person who understands a critical system isn't a sign of seniority. It's a risk for the team.

Dimension six: business and product understanding. Juniors usually receive tasks and implement them. Seniors understand why the work matters: who the users are, and what problem the feature solves. That changes how they work. When a product manager asks for a complex reporting feature, a senior might ask, "What decision will this report help you make?" and discover that a simple spreadsheet export would solve ninety percent of the need in a tenth of the time.

Notice that only the first dimension is purely technical. That's the most important insight of this talk: the journey from junior to senior is as much about how you think and work with others as it is about technology.

To see all six dimensions at once, here is a tale of two pull requests.

Two developers on the same team are given the same task: customers should receive an email when their order is shipped.

The first developer writes the code in an afternoon. When the order status changes to "shipped," the code sends an email. He tests it once with his own email address, it works, and he opens a pull request titled "email feature," with no description. Done.

The second developer starts differently. Before writing code, she asks the product manager a few questions. Should customers who opted out of emails still receive this one? What if an order is split into two shipments? Then she looks at how the system sends other emails, and reuses the existing approach instead of creating a new one.

When she writes the code, she thinks about failure. What if the email service is temporarily down? She makes sure the email is retried later, and that the shipment itself never fails just because an email couldn't be sent. What if the "shipped" event is processed twice? She makes sure the customer won't receive two identical emails. She adds tests for these cases, and a log message so the team can check whether emails are going out in production.

Her pull request has a clear description: what it does, why, the decisions she made, how she tested it, and one open question for the reviewer. After release, she checks the logs to confirm emails are going out, and lets the support team know that customers will now receive shipping notifications.

Both developers "completed the task." But look at the difference. She asked about requirements: business understanding. She thought about failures and duplicates: system thinking. She tested edge cases and checked production: ownership. She wrote a clear description and informed support: communication. And her reuse of existing patterns made the codebase easier for everyone: multiplying others.

None of what she did requires genius. It requires habits, and every one of those habits can be learned, starting with your very next task.

It also helps to see how the shape of a developer's week changes along the way.

A junior developer's week is usually dominated by focused implementation: maybe seventy or eighty percent of their time goes into writing and fixing code for well-defined tasks, with the rest spent in team meetings, asking questions, and learning.

A senior developer's week looks different. They still write code, often a significant amount, and usually the trickiest parts. But a good share of their time goes elsewhere: reviewing pull requests, discussing designs with other engineers, clarifying requirements with product managers, helping a junior colleague who's stuck, investigating a production issue, or thinking about how to remove a recurring source of bugs.

Some developers find this shift uncomfortable at first. "I'm writing less code, so am I less productive?" The answer is no. The senior's work has moved to a higher level of leverage. An hour spent clarifying requirements can save a week of building the wrong thing. An hour spent reviewing a design can prevent a month of painful rework. And an hour spent helping a junior get unstuck can save them a whole day. So if you notice your week starting to include more of these activities, don't worry that you're "coding less." It's usually a sign that you're growing.

How long does all this take? It varies enormously, depending on the company, the person, and the opportunities. In many companies, the journey from junior to senior takes somewhere around three to seven years. But some people move faster because they grow deliberately in all six dimensions, and some stay at the same level for many years because they only grew in one. Your growth isn't just a function of time. It's a function of how you use that time.

And watch out for a few traps along the way. Chasing titles instead of skills: a bigger title without matching skills becomes uncomfortable quickly, and it often shows in the next interview. Technology hopping: constantly switching to the newest framework feels like progress, but it often means staying shallow. Being the hero who works through the night to save every release: it leads to burnout and creates risk for the team. And avoiding the people side: communication and collaboration are often exactly what stops technically strong people from growing further.

A word on AI, because it's changing this journey. AI coding assistants can now generate a lot of routine code very quickly, which means some of the simple tasks juniors traditionally learned on are increasingly automated. At the same time, the skills that define seniority, judgment, system thinking, debugging, understanding the business, and responsibility for quality, are becoming even more valuable, because someone has to decide what to build and whether the AI's output is correct and secure. Use AI tools, and learn to use them well. But make sure you understand every line you submit.

Now, let's make this personal with a short exercise. Please take a piece of paper, or open a note on your phone.

[Self-assessment, about two minutes. For each of the six dimensions, participants score themselves from one to five, where one means "I'm just starting" and five means "I'm consistently strong here," and then circle the one dimension where improvement would make the biggest difference right now.]

How did that feel? Most people discover two things. They're usually stronger in the technical dimensions and weaker in communication, ownership, or business understanding. And their growth doesn't depend on learning yet another framework. It depends on deliberately working on the dimension they circled.

Three habits will help with almost any of them. First, seek feedback actively: after a project, ask a senior colleague, "What's one thing I could have done better?", and ask specifically about the dimension you circled. Second, take on work that stretches you: the messy old module, the production issue nobody can reproduce, the design discussion you'd normally just listen to. And third, keep a record of what you deliver, the problems you solve, and the people you help. When it's time for a promotion conversation, you'll remember far less than you think.

And remember, in most companies, people are promoted when they're already performing at the next level, not in the hope that they'll grow into it. So the goal is to start working like a senior, in scope, autonomy, and impact, before the title arrives.

{{ argument_closing_personal_advice }}

Let's bring it together. Being senior is not mainly about years or about knowing many technologies. It's about scope, autonomy, and impact. You grow along six dimensions: technical depth, system thinking, ownership, communication, multiplying others, and business understanding. And the difference shows up not in genius, but in habits you can start practicing on your next task.

Now, please look again at the paper where you scored yourself. Choose one action, just one, that you'll take in the next two weeks to grow in the dimension you circled. Small, deliberate steps, repeated over time, are how juniors become seniors.

Now, your questions. And keep that paper close.
