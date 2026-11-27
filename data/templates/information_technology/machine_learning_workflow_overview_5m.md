---
topic: "Machine Learning Workflow Overview"
category: "Information Technology"
duration_min: 5
---
If you train a brilliant model and nobody can ever use it, have you really built a machine learning system? Welcome, everyone, to today's session of {{ argument_course_or_event_name }}. I'm {{ argument_speaker_name }}, and that question is why today we're going to step back from individual algorithms and look at the bigger picture: the complete workflow of a machine learning project, from the first idea all the way to a model running in the real world.

When people imagine machine learning work, they picture someone choosing a clever algorithm and training a model. What surprises many newcomers is that, in real projects, that part is often a small fraction of the effort. Practitioners commonly report that most of their time goes into understanding the problem, collecting data, and cleaning it. And after the model is built, a great deal of work goes into deploying it and keeping it healthy.

Today's goal is to give you a map. Once you have this map, every algorithm you learn later will have a clear place on it.

The first question to ask is: do we even need machine learning? In my view, {{ argument_when_ml_is_needed }}.

For our churn problem, we might gather data from several sources: account information, like subscription plan and sign-up date; usage data, like hours listened per week and number of playlists created; payment history; and customer support tickets. Most importantly, we need labels: historical records showing which customers actually cancelled and which ones stayed. Without labels, supervised learning is impossible.

Stage five: split the data correctly.

And that brings us to one of the most dangerous traps in machine learning: data leakage. I would argue that {{ argument_data_leakage_danger }}.

Remember that ninety-five percent accurate model that predicted "nobody churns"? Why is it useless? Because accuracy can be very misleading when classes are imbalanced. That model never catches a single customer who's about to leave, which was the whole point of the project.

And second, a simple but powerful question to ask before any model goes live: "If this model makes a mistake, who could be harmed, and how badly?" For a music discount, the harm is small. I believe that {{ argument_harm_before_deployment }}.

Many courses end at stage seven. Real projects don't. A model sitting in a notebook on someone's laptop creates zero value.

What can we learn from this? My reading is that {{ argument_zillow_lessons }}.

{{ argument_next_step_or_assignment }}

That's the map. Which stage would you like to dig into first?
