---
topic: "Green Software: Building Software That Wastes Less"
category: "Technology"
duration_min: 20
---
When you send an email, watch a video, or ask an AI chatbot a question, where does the energy come from?

Good {{ argument_time_of_day }}, everyone. I'm {{ argument_speaker_name }}, and {{ argument_speaker_background }} Thank you for joining this session on green software: how the code we write, and the systems we design, can do the same job while wasting far less energy and hardware.

Most of us never think about it. Digital technology feels weightless. We talk about "the cloud," as if our data floated somewhere in the sky. But the cloud is made of very physical things: millions of servers in enormous buildings, cooled by fans, air conditioning, and water, and powered by electricity that, in many parts of the world, still comes largely from fossil fuels. And every device that runs our software was manufactured from metals and minerals dug out of the ground.

Estimates vary, but many studies place the information and communication technology sector's share of global greenhouse gas emissions at a few percent, broadly comparable to commonly cited figures for aviation. And demand is growing quickly, especially with AI. The International Energy Agency, for example, has projected substantial growth in electricity consumption from data centers in the coming years.

{{ argument_local_energy_context }}

Here's the part that matters for us: software decides how much hardware we need, how hard it works, and for how long. For a long time, developers didn't need to think much about this. Hardware kept getting faster and cheaper, so inefficient code was often "good enough." At today's scale, every unnecessary computation, every redundant data transfer, and every idle service running around the clock translates into real electricity, real emissions, and real money.

My goal is that you leave today not just with facts, but with a clear sense of what you, personally, can change in the code and systems you work on, starting next week.

In 2021, a group of organizations founded the Green Software Foundation, with the goal of building a community and standards for sustainable software. It promotes a simple way of thinking about green software, built on three ideas.

The first is energy efficiency: use the least amount of energy possible to do the work.

The second is hardware efficiency: use the least amount of physical hardware possible. For devices like smartphones and laptops, life-cycle assessments published by manufacturers themselves often show that manufacturing accounts for the majority of their total emissions. So software that keeps servers busy doing useful work, and that runs well on older devices, reduces the need for new hardware.

And the third is carbon awareness: do more when electricity is cleaner, and less when it's dirtier. The carbon intensity of electricity, meaning how much carbon dioxide is emitted per unit of electricity, changes with the time of day, the weather, and the location. On a sunny, windy afternoon, a grid may be powered largely by renewables. On a still evening, it may rely more on fossil fuels. Software that can be flexible about when or where it runs can take advantage of that.

The foundation has also developed a specification called the Software Carbon Intensity, or SCI, a method for calculating the emissions of a piece of software per unit of useful work, for example per user, per transaction, or per API call. Measuring "per unit of work" matters, because it allows a growing product to show that it's becoming more efficient, even as total usage grows.

So what does green software look like in practice? Seven techniques, from the most common to the more advanced.

Efficient code and algorithms. This is computer science at its most practical. Choosing an algorithm with better complexity, avoiding repeated work, and using efficient data structures can reduce computation dramatically. A classic example is the database query in a loop: fetching data one record at a time, a thousand times, instead of once with a single, well-designed query. It's slow for the user, and it wastes energy on every request.

Caching. If the same result is requested again and again, compute it once and store it. Many applications recompute or re-fetch the same data thousands of times a day.

Right-sizing and autoscaling. Many applications run on servers far larger than they need, "just in case." Choosing appropriately sized resources, and scaling automatically up when demand rises and down when it falls, can significantly cut both energy use and costs.

Turning things off. Development and test environments, demo systems, and forgotten experiments often run around the clock, even when nobody uses them at night or on weekends. Scheduling them to shut down outside working hours is one of the easiest wins available.

Managing data. Storing data costs energy, and backing it up multiplies that. Many organizations keep enormous amounts of data that nobody will ever use again: old logs, duplicate files, and abandoned datasets. Retention policies, deleting what's not needed, and moving rarely used data to lower-energy storage tiers all help.

Reducing data transfer. Every byte sent over a network uses energy, on servers, in the network, and on the user's device. Compressing images and videos, loading content only when needed, and avoiding unnecessary scripts make websites and apps lighter.

And carbon-aware scheduling. For work that doesn't need to happen immediately, such as large batch jobs, backups, or training machine learning models, you can schedule it for times or regions where electricity is cleaner. Several tools and services now provide information on grid carbon intensity, which makes this increasingly practical.

An example shows how these ideas add up.

Imagine a university's online learning platform. Every night, it generates detailed reports for thousands of courses, whether or not anyone will read them. It stores every version of every report forever. Its video lectures are uploaded in the highest possible quality, and streamed at that quality to every student, including those watching on small phone screens with weak connections. Its test servers run all the time. And its main servers are sized for the busiest day of the exam period, all year round.

Now imagine a review of this platform with green software in mind. The team generates reports only for courses where an instructor has requested them, and only when data has changed. They keep reports for one academic year, and archive older ones. They encode videos at several quality levels, and stream the one that fits each student's screen and connection. They schedule test servers to turn off at night and on weekends. And they use autoscaling, so that extra capacity is added during exam periods and removed afterward.

No single change is dramatic. But together, they can substantially reduce the computing, storage, and network resources the platform needs. And almost every one of these changes also saves money, and many improve the experience for users, especially those with older phones or weak connections. You'll see that pattern again and again: in software, sustainability and good engineering usually point in the same direction.

{{ argument_green_software_example }}

Since so many of you build websites and web applications, a bit more on sustainable web design, because it's one of the areas where individual developers can make a visible difference.

Over the past decade or so, the average web page has become much heavier. Data collected by projects such as the HTTP Archive, which regularly analyzes millions of websites, shows that typical page sizes have grown substantially, driven by larger images, more JavaScript, web fonts, videos, and third-party scripts for advertising and analytics. Every visitor downloads all of that, again and again.

A practical checklist for lighter websites: optimize images, using modern formats, the right dimensions for each screen, and compression. Load images and videos only when they're about to appear on screen, which is called lazy loading. Avoid autoplaying videos. Question every third-party script, because each analytics tool, chat widget, or tracking pixel adds weight. Limit custom fonts to what you really need. Use caching so that returning visitors don't download the same files again. And measure your page weight regularly, so that it doesn't grow quietly over time.

This checklist is the same as a checklist for a fast, accessible website. Faster pages rank better in search engines, convert better, and work better for users with older phones or expensive mobile data. So when you make a website lighter, you're helping the planet, your users, and your business at the same time.

A related practice: designing software for longevity. When an app stops supporting older operating system versions, or becomes too heavy to run smoothly on older phones, users are effectively pushed to buy new devices, even when their current ones work perfectly well. Sometimes that's unavoidable, for example for security reasons. But often, it's the result of choices nobody examined: adding a heavy library for a small feature, raising the minimum supported version because it's slightly more convenient, or never testing on older hardware. Software that works well on older and cheaper devices is not only greener. It's fairer, because those devices often belong to users with lower incomes.

No discussion of green software today would be complete without AI. Training large models requires enormous computation, but once a model is deployed, it may be used millions of times a day, and the total energy used for this everyday use, called inference, can become larger than the energy used for training.

The same principles apply. Use the right model for the task: for classification, extraction, or routing, a smaller or specialized model can often perform well, using a fraction of the computation. Start with the smallest model that might work, measure it, and only move to a larger one if needed. Avoid unnecessary calls, by caching common answers and not calling a model for tasks that simple code can do reliably. And measure the energy and cost of AI features, because without measurement, you can't make informed decisions about them.

One important warning before we practice. When a technology becomes more efficient, it often becomes cheaper to use, and so people use more of it. This is called the rebound effect, and it goes back to the economist William Stanley Jevons, who observed in the nineteenth century that more efficient steam engines led to more coal being used, not less. In IT, we see it constantly: as computing, storage, and bandwidth become cheaper, we use vastly more of them. So efficiency improvements are necessary, but on their own, they're not sufficient. We also need to ask whether we need everything we're building, running, and storing.

Now, it's time for you to apply what we've discussed.

[Practical exercise, about three minutes. Ask the audience to think of a system or project they know well, such as a website they built, an application at work, or a student project. Individually or with a neighbor, they should identify two sources of digital waste, using the categories from today: inefficient code, missing caching, oversized or idle infrastructure, data stored without purpose, heavy data transfer, or unnecessary AI calls. For each, they should write one concrete action that would reduce it. Invite two or three people to share one example each.]

I hope you noticed that it wasn't difficult to find waste. Almost every system has some. And reducing it usually saves money, too.

So, what can you do, starting next week?

If you're a software developer: treat efficiency as part of quality. Look for the obvious waste: queries in loops, missing caches, oversized images, unnecessary libraries, and repeated computation. Test on older devices and slower connections. And when you review someone else's code, it's perfectly reasonable to ask: "Is there a lighter way to do this?"

If you manage infrastructure: measure utilization, and act on it. Right-size resources, use autoscaling, turn off non-production environments when they're not in use, and make energy and cost visible to the teams that create them, because people can't optimize what they can't see.

And if you're a student: learn the fundamentals of efficiency, such as algorithms, data structures, databases, and networking, because they're also the fundamentals of green software. In your projects, measure the size of your web pages or the performance of your queries, and discuss it in your reports. Very few students can talk about this, and it's an increasingly valuable skill.

{{ argument_closing_reflection }}

The people in this room write the code and design the systems that determine much of the footprint of our digital world. That's a responsibility. It's also an opportunity, because in software, the most sustainable choice and the best engineering choice are, very often, the same choice.

My challenge to you: next week, take one action from today, just one. Measure something, turn something off, delete something you don't need, or ask one question in a meeting: "Is there a more efficient way to do this?"

I'd be glad to answer your questions, and to hear about the ideas you came up with during the exercise.
