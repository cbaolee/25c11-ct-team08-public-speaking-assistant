---
topic: "Object-Oriented Programming Pillars"
category: "Information Technology"
duration_min: 10
---
If a program can be written perfectly well with just functions and variables, why did our industry bother to invent objects at all? It's a fair question, and many people quietly wonder about it. Good {{ argument_time_of_day }}, everyone, and thank you for joining this session of {{ argument_event_or_course_name }}. I'm {{ argument_speaker_name }}, and over the next quarter of an hour or so, we're going to answer that question by exploring one of the most influential ideas in software development: object-oriented programming, and in particular, its four pillars.

If you've written code in languages like Java, C++, C#, or Python, you've almost certainly used objects, even if no one ever explained why they exist. So today, I don't just want to tell you what the four pillars are. I want to show you what problem each one solves, because once you understand the problem, the concept starts to make sense.

Some history first.

In the early days, many programs were written in a procedural style: a long list of instructions and functions operating on shared data. In my view, {{ argument_why_procedural_breaks_down }}.

Before the pillars, two quick terms. A class is a blueprint. An object is something built from that blueprint. If "Car" is the class, then my car and your car are two different objects of that class. They share the same structure, a color, a speed, a brand, but each one has its own values.

To make everything concrete today, I'll use one running example: our {{ argument_running_example_system }}. Keep this in mind as we go through each pillar.

Encapsulation means keeping an object's data and the methods that operate on that data together, and, just as importantly, hiding the internal details from the outside world.

What problem does encapsulation solve, then? I would argue that {{ argument_encapsulation_value }}.

In practice, this is why we mark fields as private and expose public methods. A useful rule of thumb: make everything as private as possible, and only open up what others really need.

Abstraction is closely related to encapsulation, and people often mix them up, so let me be precise. Encapsulation is about hiding the data and protecting it. Abstraction is about hiding complexity, showing only what is essential and leaving out unnecessary detail.

In code, abstraction often appears as abstract classes and interfaces. Imagine a payment system that supports credit cards, e-wallets, and bank transfers. We can define an abstract idea called "Payment Method" with one essential operation: pay a certain amount. The checkout code only talks to that abstraction. It doesn't care how each method actually connects to a bank or a provider.

The difference fits in one sentence: abstraction decides what to show, and encapsulation decides how to protect what is hidden.

Inheritance lets one class acquire the properties and behaviors of another class. The original class is called the parent, base, or superclass. The new one is called the child, derived, or subclass.

The key test for inheritance is the "is-a" relationship. A car is a vehicle. A savings account is a bank account. If that sentence sounds natural, inheritance may be appropriate.

However, and this is important, inheritance is also the most commonly misused pillar. My position is that {{ argument_inheritance_misuse }}.

That leaves the fourth pillar, and in many ways the most powerful one: polymorphism.

Our payment example makes this concrete. We have one abstract operation: pay. A credit card object implements pay by contacting the card network. An e-wallet implements pay by calling the wallet's API. A bank transfer implements it by generating a transfer request. The checkout code simply says: "payment method, pay this amount." It doesn't know, and doesn't need to know, which kind it's talking to. Each object responds in its own way.

Technically, there are two common forms. The first is method overriding, where a child class provides its own version of a method defined in the parent. This is decided while the program is running, and it's the form we've been discussing. The second is method overloading, where several methods share the same name but take different parameters, such as calculating an area from one number for a square, or from two numbers for a rectangle. In languages like Java and C++, this one is resolved when the code is compiled. Some languages, such as Python, don't support it in the same way.

And what does polymorphism buy us? Extensibility. Suppose next month the business wants to add a new payment method, say, {{ argument_new_feature_example }}. With polymorphism, we create one new class that implements pay. The checkout code doesn't change at all. Without polymorphism, we'd be adding yet another "if" branch to a long chain of conditions scattered throughout the codebase, and every new branch is a new chance for bugs.

Abstraction defines what an object should do, the essential contract. Encapsulation protects how it does it, keeping the internals safe. Inheritance lets related objects share common structure and behavior. And polymorphism lets us treat all those related objects uniformly, while each still behaves in its own correct way.

In our {{ argument_running_example_system }}, that means each component exposes a clean interface, guards its own data, reuses shared logic where it truly makes sense, and can be swapped or extended without rewriting the rest of the system.

First, don't treat the pillars as rules to follow blindly. Treat them as tools for managing complexity. If a design is getting harder to understand, ask which pillar could help.

And one honest note: object-oriented programming isn't the only way to build software. I believe that {{ argument_oop_not_only_paradigm }}.

In four short phrases: encapsulation protects data, abstraction hides complexity, inheritance enables reuse, and polymorphism enables flexibility. Together, they help us build software that can grow without collapsing under its own weight.

I'll stop here and hand the floor to you: where have these pillars saved you in your own code, and where did they get in your way?
