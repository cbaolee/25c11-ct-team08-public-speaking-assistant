---
topic: "Machine Learning Workflow Overview"
category: "Information Technology"
duration_min: 10
---
If you train a brilliant model and nobody can ever use it, have you really built a machine learning system? Welcome, everyone, to today's session of {{ argument_course_or_event_name }}. I'm {{ argument_speaker_name }}, and that question is why today we're going to step back from individual algorithms and look at the bigger picture: the complete workflow of a machine learning project, from the first idea all the way to a model running in the real world.

When people imagine machine learning work, they picture someone choosing a clever algorithm and training a model. What surprises many newcomers is that, in real projects, that part is often a small fraction of the effort. Practitioners commonly report that most of their time goes into understanding the problem, collecting data, and cleaning it. And after the model is built, a great deal of work goes into deploying it and keeping it healthy.

Today's goal is to give you a map. Once you have this map, every algorithm you learn later will have a clear place on it.

We'll carry that request through the whole workflow.

The first question to ask is: do we even need machine learning? In my view, {{ argument_when_ml_is_needed }}.

In our case, churn depends on many interacting factors, listening habits, payment history, customer service contacts, so machine learning makes sense.

Stage two: collect the data.

At this stage, we should also ask some hard questions. Do we have enough data? Is it representative of all our customers, or only some of them? Are we legally and ethically allowed to use it? In many countries, personal data is protected by law, so privacy must be considered from day one, not at the end.

Some values will be missing. Maybe some customers never filled in their age. We have to decide: do we remove those rows, fill in a reasonable value like the median, or treat "missing" as its own category? Each choice has consequences.

And here we also do something called feature engineering: creating new, more meaningful inputs from the raw data. Rather than just using "total hours listened," we might create "change in listening time compared with last month." A customer whose listening suddenly drops by eighty percent is a much stronger signal of churn than any raw number alone. Good feature engineering, guided by domain knowledge, often improves a model more than switching to a fancier algorithm.

We look at distributions, relationships, and charts, and we often discover surprises. One finding in particular deserves attention: class imbalance. In our example, perhaps only five percent of customers churn each month. That means ninety-five percent of our examples are "stayed." Keep that number in mind, because it's going to matter a lot when we evaluate the model.

Picture a student who memorizes the answers to last year's exam. They might score one hundred percent on that exam, but it tells us nothing about whether they understand the subject. A model can do the same thing: memorize its training data perfectly and fail completely on new data.

And that brings us to one of the most dangerous traps in machine learning: data leakage. I would argue that {{ argument_data_leakage_danger }}.

Stage six: build and train models.

Then we try more powerful models. For structured, table-like data like ours, tree-based ensemble methods, such as random forests and gradient boosting, are often among the best performers. Deep neural networks shine especially with unstructured data like images, audio, and text, but they're not always the best choice for tables of numbers.

Remember that ninety-five percent accurate model that predicted "nobody churns"? Why is it useless? Because accuracy can be very misleading when classes are imbalanced. That model never catches a single customer who's about to leave, which was the whole point of the project.

Recall answers the question: of all the customers who actually churned, how many did the model catch? High recall means we miss very few customers who are about to leave.

Only after all of this, when we've chosen our final model, do we unlock the test set and evaluate it once. That number is our honest estimate of real-world performance.

In our churn project, that means asking two honest questions. First: could the model treat some groups of customers unfairly? For example, if it rarely offers discounts to older customers, simply because they were underrepresented in the data, that's a problem worth fixing.

And second, a simple but powerful question to ask before any model goes live: "If this model makes a mistake, who could be harmed, and how badly?" For a music discount, the harm is small. I believe that {{ argument_harm_before_deployment }}.

Deployment means integrating the model into the real system. For our churn model, it might run every night, score every active customer, and send a list of high-risk customers to the marketing team's tools. In other cases, a model might be served through an API, answering requests in real time, like a fraud detection system that has to approve or block a payment within milliseconds.

And finally, we close the loop by asking the business question again: did churn actually go down? A model with excellent precision and recall that doesn't change any business outcome hasn't really succeeded.

Then the housing market changed quickly, in ways that the historical data hadn't prepared the models for. The estimates of what houses would be worth in a few months turned out to be too optimistic, and the company ended up owning many homes worth less than it had paid. In November twenty twenty-one, Zillow announced that it was shutting down Zillow Offers, took a write-down of hundreds of millions of dollars on its housing inventory, and cut about a quarter of its workforce.

What can we learn from this? My reading is that {{ argument_zillow_lessons }}.

{{ argument_next_step_or_assignment }}

That's the map. Which stage would you like to dig into first?
