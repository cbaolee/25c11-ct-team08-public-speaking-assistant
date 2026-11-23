---
topic: "Machine Learning Workflow Overview"
category: "Information Technology"
duration_min: 15
---
If you train a brilliant model and nobody can ever use it, have you really built a machine learning system? Welcome, everyone, to today's session of {{ argument_course_or_event_name }}. I'm {{ argument_speaker_name }}, and that question is why today we're going to step back from individual algorithms and look at the bigger picture: the complete workflow of a machine learning project, from the first idea all the way to a model running in the real world.

When people imagine machine learning work, they picture someone choosing a clever algorithm and training a model. What surprises many newcomers is that, in real projects, that part is often a small fraction of the effort. Practitioners commonly report that most of their time goes into understanding the problem, collecting data, and cleaning it. And after the model is built, a great deal of work goes into deploying it and keeping it healthy.

Today's goal is to give you a map. Once you have this map, every algorithm you learn later will have a clear place on it.

We'll go through eight stages: defining the problem, collecting data, preparing the data, exploring it, splitting it correctly, building and training models, evaluating them, and finally deploying and monitoring. I'll also point out the most common traps at each stage, and share a real case study, because many machine learning failures don't come from bad algorithms; they come from mistakes in the workflow.

We'll carry that request through the whole workflow.

This sounds obvious, but it's the stage where many projects go wrong, because a vague goal leads to a model that answers the wrong question.

The first question to ask is: do we even need machine learning? In my view, {{ argument_when_ml_is_needed }}.

The next move is to translate the business question into a machine learning task. What exactly are we predicting? Here, it's a yes-or-no answer: will this customer cancel within the next thirty days? That makes it a classification problem, specifically binary classification. If instead we wanted to predict how many songs a user will play next week, that would be a regression problem, because the answer is a number. And if we just wanted to group customers into similar segments without any labels, that would be clustering, which is a form of unsupervised learning.

Stage two: collect the data.

For our churn problem, we might gather data from several sources: account information, like subscription plan and sign-up date; usage data, like hours listened per week and number of playlists created; payment history; and customer support tickets. Most importantly, we need labels: historical records showing which customers actually cancelled and which ones stayed. Without labels, supervised learning is impossible.

At this stage, we should also ask some hard questions. Do we have enough data? Is it representative of all our customers, or only some of them? Are we legally and ethically allowed to use it? In many countries, personal data is protected by law, so privacy must be considered from day one, not at the end.

This is the stage that famously takes the most time, and for good reason. Real-world data is messy.

Some values will be wrong or inconsistent. A customer with an age of two hundred, the same country written as "Vietnam," "Viet Nam," and "VN," or duplicate records for the same person. These need to be found and fixed.

And here we also do something called feature engineering: creating new, more meaningful inputs from the raw data. Rather than just using "total hours listened," we might create "change in listening time compared with last month." A customer whose listening suddenly drops by eighty percent is a much stronger signal of churn than any raw number alone. Good feature engineering, guided by domain knowledge, often improves a model more than switching to a fancier algorithm.

Before training anything, we need to understand what we're working with. This is called exploratory data analysis.

Stage five: split the data correctly.

Now we come to a rule that is simple, absolutely essential, and still broken surprisingly often: never evaluate a model on the same data it learned from.

The standard answer is to split the data into three parts. The training set, usually the largest, is what the model learns from. The validation set is used to compare different models and tune their settings. And the test set is locked away until the very end, and used only once, to get an honest estimate of how the final model will perform on new, unseen data.

And that brings us to one of the most dangerous traps in machine learning: data leakage. I would argue that {{ argument_data_leakage_danger }}.

Stage six: build and train models.

The golden rule here is: start simple. Before trying anything sophisticated, build a baseline. The simplest baseline could be: "predict that nobody churns." With our five percent churn rate, this "model" would be ninety-five percent accurate, and completely useless. That's actually a valuable lesson, and we'll see why in a moment.

As we train, we need to watch out for two opposite problems. Underfitting means the model is too simple to capture the real patterns. It performs poorly on both training and validation data, like a student who didn't study. Overfitting means the model has learned the training data too well, including its noise and random quirks. It performs brilliantly on the training data, but poorly on new data, like the student who memorized last year's exam. Our goal is the sweet spot in between: a model that generalizes.

Remember that ninety-five percent accurate model that predicted "nobody churns"? Why is it useless? Because accuracy can be very misleading when classes are imbalanced. That model never catches a single customer who's about to leave, which was the whole point of the project.

Problems like ours need better metrics. Two of the most important ones are easiest to explain with our example.

Recall answers the question: of all the customers who actually churned, how many did the model catch? High recall means we miss very few customers who are about to leave.

For regression problems, we'd use different metrics, such as the average size of our errors. And beyond the numbers, we should also look at where the model fails. Does it perform much worse for certain groups of customers, such as older users or people in certain regions? A model that is accurate on average but unfair to a particular group can cause real harm, and that's something we must check before going any further.

Before we move on to deployment, I want to spend a few more minutes on something that is far too important to be treated as a footnote: responsible machine learning.

In our churn project, that means asking two honest questions. First: could the model treat some groups of customers unfairly? For example, if it rarely offers discounts to older customers, simply because they were underrepresented in the data, that's a problem worth fixing.

And second, a simple but powerful question to ask before any model goes live: "If this model makes a mistake, who could be harmed, and how badly?" For a music discount, the harm is small. I believe that {{ argument_harm_before_deployment }}.

Many courses end at stage seven. Real projects don't. A model sitting in a notebook on someone's laptop creates zero value.

Deployment means integrating the model into the real system. For our churn model, it might run every night, score every active customer, and send a list of high-risk customers to the marketing team's tools. In other cases, a model might be served through an API, answering requests in real time, like a fraud detection system that has to approve or block a payment within milliseconds.

So we monitor. We track the model's predictions, compare them with what actually happens, watch for changes in the input data, and retrain the model regularly with fresh data. The practices and tools for doing this reliably, automating training, testing, deployment, and monitoring, are known as MLOps, short for machine learning operations.

A well-known case shows what happens when a real company gets parts of this workflow wrong.

Then the housing market changed quickly, in ways that the historical data hadn't prepared the models for. The estimates of what houses would be worth in a few months turned out to be too optimistic, and the company ended up owning many homes worth less than it had paid. In November twenty twenty-one, Zillow announced that it was shutting down Zillow Offers, took a write-down of hundreds of millions of dollars on its housing inventory, and cut about a quarter of its workforce.

What can we learn from this? My reading is that {{ argument_zillow_lessons }}.

Define the problem clearly, and decide whether machine learning is even needed. Collect relevant, representative, and legally usable data, with labels. Clean and transform it, and engineer meaningful features. Explore it to understand patterns and problems, like class imbalance. Split it properly, and guard against data leakage. Start with a simple baseline, then try stronger models, while avoiding underfitting and overfitting. Evaluate with metrics that match the business goal, check for fairness, and use the test set only once. And finally, deploy, monitor for drift, and retrain, closing the loop with the business.

{{ argument_next_step_or_assignment }}

That's the map. Which stage would you like to dig into first?
