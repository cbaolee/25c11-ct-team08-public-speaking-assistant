---
topic: "How Large Language Models Work"
category: "Technology"
duration_min: 12
---
When you type a question into ChatGPT, Claude, or Gemini, and a fluent answer appears word by word, it can feel as if someone is thinking on the other side of the screen. Good {{ time_of_day }}, everyone. I'm {{ speaker_name }}, and today I want to open up that box, which many of us use every day but rarely look inside: large language models.

But first, a small experiment. I'm going to say the beginning of a sentence, and I want you to finish it in your head. Ready? "Once upon a..."

I'm pretty sure almost everyone thought "time." Now, how did you know that? Nobody gave you a rule. You've simply seen and heard that phrase so many times that your brain predicts what comes next.

That tiny experiment captures the core idea of a large language model. At its heart, a large language model is a system that has learned to predict what comes next in a piece of text. That's the whole trick. The surprising part, and the reason these tools feel so impressive, is how much can emerge from doing that one thing extremely well, at an enormous scale.

We'll go step by step, and I promise, no complicated math.

How does a model read? With tokens.

Computers don't read words the way we do. A language model's first job is to break text into small pieces called tokens. A token might be a whole word, like "cat," or part of a word. For example, a long word like "unbelievable" might be split into pieces like "un," "believ," and "able." As a rough rule of thumb, in English, one token is about three quarters of a word.

Each token is then turned into a list of numbers. During training, something elegant happens: the model learns to place words with similar meanings close to each other in this space of numbers. "King" ends up near "queen." "Paris" ends up near "France." In other words, meaning becomes something the computer can measure. These lists of numbers are called embeddings.

How does it learn? By predicting the next token.

The model is trained on a massive amount of text: books, websites, articles, code, and much more, often trillions of tokens in total. During training, the model is shown a piece of text with the next token hidden, and it has to guess what it is.

At first, its guesses are completely random. But every time it guesses, its answer is compared with the real one, and the model adjusts itself slightly to make a better guess next time. Then it does this again. And again. Billions and billions of times.

What exactly is being adjusted? Inside the model is a huge neural network, a mathematical structure loosely inspired by the brain, made of connections with numerical values called parameters. You can imagine them as tiny knobs. Modern large models have billions, sometimes hundreds of billions, of these knobs. Training is the process of slowly turning all of them until the model becomes very, very good at predicting text.

Something remarkable happens along the way. To predict the next word really well, the model has to learn far more than grammar. To finish a sentence about history, it helps to know facts. To finish a line of code, it helps to understand programming. To finish a joke, it helps to recognize humor. Nobody programmed these skills directly. They emerged from the pressure of prediction.

How does it keep track of context? With the transformer and attention.

The architecture behind all of this is surprisingly young. In twenty seventeen, a team of researchers at Google published a paper with a memorable title: "Attention Is All You Need." It introduced an architecture called the transformer, and that's what the "T" in "GPT" stands for.

The key idea in the transformer is something called attention. Attention lets the model look at all the words in a passage at once and decide which ones matter most for understanding each word.

Consider the sentence: "The trophy didn't fit in the suitcase because it was too big." What does "it" refer to? The trophy. Now change one word: "The trophy didn't fit in the suitcase because it was too small." Now "it" refers to the suitcase. As humans, we resolve this instantly. Attention is what lets the model do the same thing: when processing the word "it," it can focus strongly on "trophy" or on "suitcase," depending on the context.

Before transformers, models read text more or less one word at a time and tended to forget the beginning of long passages. Attention, combined with the ability to process text in parallel on powerful graphics chips, made it possible to train much larger models on much more data. That's the "large" in "large language model."

How does a text predictor become a helpful assistant?

If we stopped after training on internet text, we'd have a model that's great at continuing text, but not necessarily good at being helpful. Ask it a question, and it might respond with five more questions, because that's what it saw on some quiz website.

A second phase of training fixes that. First, the model is fine-tuned on many examples of good conversations: a question followed by a helpful, well-written answer. Then, people rate or compare the model's responses, and those ratings are used to further train the model toward answers that are helpful, honest, and safe. One widely used approach is called reinforcement learning from human feedback.

This is what turns a raw text predictor into the polite, structured assistant you chat with.

And how does an answer actually get written?

Type a question, and this is what follows. Your message is split into tokens. The model processes all of them, using attention to understand the context. Then it produces a probability for every possible next token, for example, "Paris" with ninety-five percent, "Lyon" with two percent, and so on. It picks one, adds it to the text, and then repeats the whole process to predict the next token, one token at a time, until the answer is complete. That's why you often see the response appear word by word.

There's also a setting called temperature, which controls how adventurous the model is when picking tokens. Low temperature makes it choose the most likely options, which is good for facts and code. Higher temperature lets it choose less likely options, which can be good for creative writing.

And there's a limit to how much text the model can consider at once, called the context window. Anything outside that window, the model simply cannot see.

The important part comes next: what language models can't do well.

Understanding how they work also explains their weaknesses.

First, hallucinations. Because the model generates text that is likely, not text that is verified, it can produce answers that sound confident and fluent but are completely wrong, including made-up facts, quotes, or references. It isn't lying on purpose; it simply doesn't have a built-in sense of truth.

Second, knowledge cutoff. The model learns from data collected up to a certain date. Unless it's connected to tools like web search, it doesn't know about events after that.

Third, bias. The model learns from human-written text, and human text contains biases. Developers work hard to reduce this, but it can never be completely removed.

And fourth, the deeper question: does the model truly understand? This is still debated among researchers. Some argue that models build genuine internal representations of the world. Others say they are extremely sophisticated pattern-matchers. What we can say is that they can be remarkably capable, and also surprisingly fragile, sometimes failing at tasks that seem simple to us.

So how should we use them wisely?

Treat a language model like a brilliant, very fast assistant who sometimes makes things up. Give it clear instructions and enough context. Use it to draft, brainstorm, explain, and summarize. And always verify anything important: facts, numbers, legal or medical information, and code before you run it in production.

{{ everyday_use_example }}

Putting it together: large language models break text into tokens and represent meaning as numbers. They learn by predicting the next token across enormous amounts of text, adjusting billions of parameters along the way. The transformer architecture, with its attention mechanism, lets them understand context at scale. Additional training with human feedback turns them into helpful assistants. And they generate answers one token at a time, which makes them fluent, but not always correct.

So the next time an AI writes you a perfect paragraph in two seconds, remember: behind it is a machine that has become extraordinarily good at one question, asked again and again: "What comes next?"

Questions? Bring me the hard ones, the kind a chatbot would answer with great confidence and get wrong.
