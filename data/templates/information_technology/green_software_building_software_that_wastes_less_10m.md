---
topic: "Green Software: Building Software That Wastes Less"
category: "Information Technology"
duration_min: 10
---
When you send an email, watch a video, or ask an AI chatbot a question, where does the energy come from?

Good {{ argument_time_of_day }}, everyone. I'm {{ argument_speaker_name }}, and {{ argument_speaker_background }} Thank you for joining this session on green software: how the code we write, and the systems we design, can do the same job while wasting far less energy and hardware.

Most of us never think about it. Digital technology feels weightless. We talk about "the cloud," as if our data floated somewhere in the sky. But the cloud is made of very physical things: millions of servers in enormous buildings, cooled by fans, air conditioning, and water, and powered by electricity that, in many parts of the world, still comes largely from fossil fuels. And every device that runs our software was manufactured from metals and minerals dug out of the ground.

{{ argument_local_energy_context }}

Here's the part that matters for us: software decides how much hardware we need, how hard it works, and for how long. I would argue that {{ argument_software_drives_hardware_footprint }}.

My goal is that you leave today not just with facts, but with a clear sense of what you, personally, can change in the code and systems you work on, starting next week.

The first is energy efficiency: use the least amount of energy possible to do the work.

And the third is carbon awareness: do more when electricity is cleaner, and less when it's dirtier. The carbon intensity of electricity, meaning how much carbon dioxide is emitted per unit of electricity, changes with the time of day, the weather, and the location. On a sunny, windy afternoon, a grid may be powered largely by renewables. On a still evening, it may rely more on fossil fuels. Software that can be flexible about when or where it runs can take advantage of that.

So what does green software look like in practice? Seven techniques, from the most common to the more advanced.

Caching. If the same result is requested again and again, compute it once and store it. Many applications recompute or re-fetch the same data thousands of times a day.

Turning things off. Development and test environments, demo systems, and forgotten experiments often run around the clock, even when nobody uses them at night or on weekends. Scheduling them to shut down outside working hours is one of the easiest wins available.

Reducing data transfer. Every byte sent over a network uses energy, on servers, in the network, and on the user's device. Compressing images and videos, loading content only when needed, and avoiding unnecessary scripts make websites and apps lighter.

Imagine a university's online learning platform. Every night, it generates detailed reports for thousands of courses, whether or not anyone will read them. It stores every version of every report forever. Its video lectures are uploaded in the highest possible quality, and streamed at that quality to every student, including those watching on small phone screens with weak connections. Its test servers run all the time. And its main servers are sized for the busiest day of the exam period, all year round.

No single change is dramatic. In my view, {{ argument_small_changes_add_up }}.

{{ argument_green_software_example }}

Since so many of you build websites and web applications, a bit more on sustainable web design, because it's one of the areas where individual developers can make a visible difference.

A practical checklist for lighter websites: optimize images, using modern formats, the right dimensions for each screen, and compression. Load images and videos only when they're about to appear on screen, which is called lazy loading. Avoid autoplaying videos. Question every third-party script, because each analytics tool, chat widget, or tracking pixel adds weight. Limit custom fonts to what you really need. Use caching so that returning visitors don't download the same files again. And measure your page weight regularly, so that it doesn't grow quietly over time.

This checklist is the same as a checklist for a fast, accessible website. My position is that {{ argument_green_equals_good_engineering }}.

No discussion of green software today would be complete without AI. Training large models requires enormous computation, but once a model is deployed, it may be used millions of times a day, and the total energy used for this everyday use, called inference, can become larger than the energy used for training.

One important warning before we practice. I believe that {{ argument_rebound_effect_warning }}.

Now, it's time for you to apply what we've discussed.

So, what can you do, starting next week?

If you manage infrastructure: measure utilization, and act on it. Right-size resources, use autoscaling, turn off non-production environments when they're not in use, and make energy and cost visible to the teams that create them, because people can't optimize what they can't see.

{{ argument_closing_reflection }}

My challenge to you: next week, take one action from today, just one. Measure something, turn something off, delete something you don't need, or ask one question in a meeting: "Is there a more efficient way to do this?"

I'd be glad to answer your questions, and to hear about the ideas you came up with during the exercise.
