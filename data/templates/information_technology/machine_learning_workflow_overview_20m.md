---
topic: "Machine Learning Workflow Overview"
category: "Technology"
duration_min: 20
---
If you train a brilliant model and nobody can ever use it, have you really built a machine learning system? Welcome, everyone, to today's session of {{ argument_course_or_event_name }}. I'm {{ argument_speaker_name }}, and that question is why today we're going to step back from individual algorithms and look at the bigger picture: the complete workflow of a machine learning project, from the first idea all the way to a model running in the real world.

When people imagine machine learning work, they picture someone choosing a clever algorithm and training a model. What surprises many newcomers is that, in real projects, that part is often a small fraction of the effort. Practitioners commonly report that most of their time goes into understanding the problem, collecting data, and cleaning it. And after the model is built, a great deal of work goes into deploying it and keeping it healthy.

Today's goal is to give you a map. Once you have this map, every algorithm you learn later will have a clear place on it.

We'll go through eight stages: defining the problem, collecting data, preparing the data, exploring it, splitting it correctly, building and training models, evaluating them, and finally deploying and monitoring. I'll also point out the most common traps at each stage, and share a real case study, because many machine learning failures don't come from bad algorithms; they come from mistakes in the workflow.

To keep things concrete, let's use one running example throughout. Imagine we work for a music streaming company. Every month, some subscribers cancel. In business language, this is called churn. Our manager asks: "Can we predict which customers are likely to cancel next month, so we can offer them a discount before they leave?"

We'll carry that request through the whole workflow.

Stage one: define the problem.

This sounds obvious, but it's the stage where many projects go wrong, because a vague goal leads to a model that answers the wrong question.

The first question to ask is: do we even need machine learning? If a simple rule works, say, "customers whose card payment failed are likely to leave," then maybe a rule is enough. Machine learning is worth it when patterns are too complex for simple rules, and when we have enough data to learn them.

In our case, churn depends on many interacting factors, listening habits, payment history, customer service contacts, so machine learning makes sense.

The next move is to translate the business question into a machine learning task. What exactly are we predicting? Here, it's a yes-or-no answer: will this customer cancel within the next thirty days? That makes it a classification problem, specifically binary classification. If instead we wanted to predict how many songs a user will play next week, that would be a regression problem, because the answer is a number. And if we just wanted to group customers into similar segments without any labels, that would be clustering, which is a form of unsupervised learning.

Finally, and this is crucial, we define what success looks like, both for the business and for the model. The business goal might be: reduce churn by five percent within six months. The model goal might be: correctly identify most of the customers who will actually leave, without flooding the marketing team with false alarms. We'll come back to this when we talk about metrics.

Stage two: collect the data.

A machine learning model is only as good as the data it learns from. As the old saying goes: garbage in, garbage out.

For our churn problem, we might gather data from several sources: account information, like subscription plan and sign-up date; usage data, like hours listened per week and number of playlists created; payment history; and customer support tickets. Most importantly, we need labels: historical records showing which customers actually cancelled and which ones stayed. Without labels, supervised learning is impossible.

At this stage, we should also ask some hard questions. Do we have enough data? Is it representative of all our customers, or only some of them? Are we legally and ethically allowed to use it? In many countries, personal data is protected by law, so privacy must be considered from day one, not at the end.

Stage three: prepare and clean the data.

This is the stage that famously takes the most time, and for good reason. Real-world data is messy.

Some values will be missing. Maybe some customers never filled in their age. We have to decide: do we remove those rows, fill in a reasonable value like the median, or treat "missing" as its own category? Each choice has consequences.

Some values will be wrong or inconsistent. A customer with an age of two hundred, the same country written as "Vietnam," "Viet Nam," and "VN," or duplicate records for the same person. These need to be found and fixed.

Then, we transform the data into a form that algorithms can use. Most algorithms only understand numbers, so categories like subscription plan, "free," "student," or "premium," need to be encoded as numbers. And many algorithms work better when numerical features are on similar scales, so we often normalize them. Otherwise, a feature measured in thousands, like minutes listened, could overpower one measured in single digits, like number of devices.

And here we also do something called feature engineering: creating new, more meaningful inputs from the raw data. Rather than just using "total hours listened," we might create "change in listening time compared with last month." A customer whose listening suddenly drops by eighty percent is a much stronger signal of churn than any raw number alone. Good feature engineering, guided by domain knowledge, often improves a model more than switching to a fancier algorithm.

Stage four: explore the data.

Before training anything, we need to understand what we're working with. This is called exploratory data analysis.

We look at distributions, relationships, and charts, and we often discover surprises. One finding in particular deserves attention: class imbalance. In our example, perhaps only five percent of customers churn each month. That means ninety-five percent of our examples are "stayed." Keep that number in mind, because it's going to matter a lot when we evaluate the model.

Stage five: split the data correctly.

Now we come to a rule that is simple, absolutely essential, and still broken surprisingly often: never evaluate a model on the same data it learned from.

Picture a student who memorizes the answers to last year's exam. They might score one hundred percent on that exam, but it tells us nothing about whether they understand the subject. A model can do the same thing: memorize its training data perfectly and fail completely on new data.

The standard answer is to split the data into three parts. The training set, usually the largest, is what the model learns from. The validation set is used to compare different models and tune their settings. And the test set is locked away until the very end, and used only once, to get an honest estimate of how the final model will perform on new, unseen data.

One important detail: for data that changes over time, like ours, we should split by time: train on older months and test on more recent months. Otherwise, we're accidentally letting the model peek into the future.

And that brings us to one of the most dangerous traps in machine learning: data leakage. Data leakage happens when information that wouldn't be available at prediction time sneaks into the training data. Suppose our dataset includes a column called "cancellation reason." The model will learn that whenever this column is filled in, the customer churned, and it will look incredibly accurate. But in real life, we only know the cancellation reason after the customer has already left. That makes the model useless. Whenever a model seems too good to be true, suspect leakage first.

Stage six: build and train models.

Finally, the part everyone was waiting for.

The golden rule here is: start simple. Before trying anything sophisticated, build a baseline. The simplest baseline could be: "predict that nobody churns." With our five percent churn rate, this "model" would be ninety-five percent accurate, and completely useless. That's actually a valuable lesson, and we'll see why in a moment.

Then we try more powerful models. For structured, table-like data like ours, tree-based ensemble methods, such as random forests and gradient boosting, are often among the best performers. Deep neural networks shine especially with unstructured data like images, audio, and text, but they're not always the best choice for tables of numbers.

As we train, we need to watch out for two opposite problems. Underfitting means the model is too simple to capture the real patterns. It performs poorly on both training and validation data, like a student who didn't study. Overfitting means the model has learned the training data too well, including its noise and random quirks. It performs brilliantly on the training data, but poorly on new data, like the student who memorized last year's exam. Our goal is the sweet spot in between: a model that generalizes.

Stage seven: evaluate the model properly.

Remember that ninety-five percent accurate model that predicted "nobody churns"? Why is it useless? Because accuracy can be very misleading when classes are imbalanced. That model never catches a single customer who's about to leave, which was the whole point of the project.

Problems like ours need better metrics. Two of the most important ones are easiest to explain with our example.

Precision answers the question: of all the customers the model flagged as "likely to churn," how many actually churned? High precision means few false alarms, so the marketing team doesn't waste discounts on happy customers.

Recall answers the question: of all the customers who actually churned, how many did the model catch? High recall means we miss very few customers who are about to leave.

There's usually a trade-off between the two. If we flag almost everyone, recall is high but precision is terrible. If we only flag the most obvious cases, precision is high but we miss many people. The F1 score combines both into a single number. But the right balance is ultimately a business decision. Here, a discount costs money, but losing a subscriber costs more, so we might accept lower precision in exchange for higher recall.

For regression problems, we'd use different metrics, such as the average size of our errors. And beyond the numbers, we should also look at where the model fails. Does it perform much worse for certain groups of customers, such as older users or people in certain regions? A model that is accurate on average but unfair to a particular group can cause real harm, and that's something we must check before going any further.

Only after all of this, when we've chosen our final model, do we unlock the test set and evaluate it once. That number is our honest estimate of real-world performance.

Before we move on to deployment, I want to spend a few more minutes on something that is far too important to be treated as a footnote: responsible machine learning.

A model learns from historical data, and historical data reflects the world as it was, including its unfairness. Nobody has to program a model to discriminate. It can simply learn the patterns in its data.

In our churn project, that means asking two honest questions. First: could the model treat some groups of customers unfairly? For example, if it rarely offers discounts to older customers, simply because they were underrepresented in the data, that's a problem worth fixing.

And second, a simple but powerful question to ask before any model goes live: "If this model makes a mistake, who could be harmed, and how badly?" For a music discount, the harm is small. For a model that approves loans or screens patients, it can be enormous, and the level of care must match.

Stage eight: deploy and monitor.

Many courses end at stage seven. Real projects don't. A model sitting in a notebook on someone's laptop creates zero value.

Deployment means integrating the model into the real system. For our churn model, it might run every night, score every active customer, and send a list of high-risk customers to the marketing team's tools. In other cases, a model might be served through an API, answering requests in real time, like a fraud detection system that has to approve or block a payment within milliseconds.

And after deployment, the work continues, because the world changes. Customer behavior shifts. A competitor launches a cheaper plan. A new feature changes how people use the app. The patterns the model learned slowly become outdated. This is called model drift, or data drift, and it means performance can quietly decline over time without anyone noticing.

So we monitor. We track the model's predictions, compare them with what actually happens, watch for changes in the input data, and retrain the model regularly with fresh data. The practices and tools for doing this reliably, automating training, testing, deployment, and monitoring, are known as MLOps, short for machine learning operations.

And finally, we close the loop by asking the business question again: did churn actually go down? A model with excellent precision and recall that doesn't change any business outcome hasn't really succeeded.

A well-known case shows what happens when a real company gets parts of this workflow wrong.

A few years ago, the American real estate company Zillow ran a business called Zillow Offers. The idea was simple: use machine learning models to estimate the value of a house, buy homes directly from owners, make small repairs, and sell them again for a profit. The models were trained on enormous amounts of historical housing data, and the company bought thousands of homes based on their predictions.

Then the housing market changed quickly, in ways that the historical data hadn't prepared the models for. The estimates of what houses would be worth in a few months turned out to be too optimistic, and the company ended up owning many homes worth less than it had paid. In November twenty twenty-one, Zillow announced that it was shutting down Zillow Offers, took a write-down of hundreds of millions of dollars on its housing inventory, and cut about a quarter of its workforce.

What can we learn from this? Analysts debated the exact causes, but notice how many of today's stages appear in the story. The model was used for a very high-stakes decision, buying houses, where errors were extremely expensive, so the definition of success and the tolerance for error mattered enormously. The world changed after the model was trained, which is exactly the drift problem we discussed in stage eight. And predictions were acted on at a very large scale, so small errors multiplied quickly. The lesson is not that machine learning failed. The lesson is that a model's limits must be understood and monitored, especially when the stakes are high and the world is changing.

The whole map, stage by stage.

Define the problem clearly, and decide whether machine learning is even needed. Collect relevant, representative, and legally usable data, with labels. Clean and transform it, and engineer meaningful features. Explore it to understand patterns and problems, like class imbalance. Split it properly, and guard against data leakage. Start with a simple baseline, then try stronger models, while avoiding underfitting and overfitting. Evaluate with metrics that match the business goal, check for fairness, and use the test set only once. And finally, deploy, monitor for drift, and retrain, closing the loop with the business.

If you remember just three lessons from today, let them be these. First, the problem and the data matter more than the algorithm. Second, be suspicious of results that look too good; they often hide leakage or a misleading metric. And third, a model is never finished; it lives in a changing world.

{{ argument_next_step_or_assignment }}

That's the map. Which stage would you like to dig into first?
