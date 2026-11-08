---
topic: "Docker and Containers for Beginners"
category: "Technology"
duration_min: 15
---
"But it works on my machine." Raise your hand if you've ever heard that sentence, or said it yourself. Yes, I see a lot of hands, and a few guilty smiles.

Good {{ argument_time_of_day }}, everyone, and welcome to {{ argument_workshop_name }}. I'm {{ argument_speaker_name }}, and I'll be your guide today as we take our first steps into the world of containers and Docker.

That sentence is one of the oldest jokes in software development, and it's exactly the problem Docker was created to solve. That's where we'll start.

Why do we need containers?

Imagine you've built a web application on your laptop. It runs perfectly. Then you send it to a teammate, and it crashes. Why? Maybe they have a different version of Python. Maybe a library is missing. Maybe their operating system handles file paths differently. Then you deploy it to a server, and something else breaks, because the server has its own configuration.

The application itself didn't change. What changed was the environment around it: the operating system, the language runtime, the libraries, the settings. And setting up that environment by hand, again and again, on every machine, is slow and full of mistakes.

Containers solve this by packaging the application together with everything it needs to run. Not just the code, but the runtime, the libraries, the configuration, all bundled into one unit. If it runs in a container on your laptop, it will run the same way in a container on your teammate's laptop, on a test server, or in the cloud.

The name itself comes from an analogy: shipping containers. For centuries, loading a cargo ship was slow and messy. Every item, sacks of coffee, barrels of oil, boxes of machinery, had a different shape and had to be handled differently. Then, in the nineteen fifties, the standard steel shipping container was introduced. Suddenly, it didn't matter what was inside. Every container had the same size and the same corners, so any ship, truck, or crane in the world could handle it. Global trade became dramatically faster and cheaper.

Software containers do the same thing. Whatever is inside, a Python web app, a Java service, a database, the container looks the same from the outside, so any machine running Docker can handle it.

Some of you might be thinking: "Isn't that what virtual machines do?" Good question. Let's compare.

A virtual machine pretends to be a complete computer. It runs its own full operating system on top of your real one, with the help of software called a hypervisor. That means each virtual machine includes an entire operating system, which can take gigabytes of space and a minute or more to start.

A container is much lighter. Instead of carrying its own full operating system, it shares the kernel, the core of the operating system, with the host machine. It only packages the application and the specific files and libraries it needs. As a result, containers are usually measured in megabytes rather than gigabytes, and they can start in a second or two.

A housing analogy captures the difference. Virtual machines are like separate houses, each with its own foundation, plumbing, and electricity. Containers are like apartments in the same building: each one is private and has its own space, but they share the foundation and the main utilities.

That doesn't mean virtual machines are obsolete. They provide stronger isolation, and they can run a completely different operating system. In the cloud, containers very often run inside virtual machines. The two technologies work together.

So where does Docker fit in?

Containers as a concept existed before Docker, using features built into the Linux kernel. But they were complicated to use. Docker, released in twenty thirteen, made containers simple and accessible to everyday developers, and it quickly became the standard tool. Today, when people say "containers," they very often mean Docker, although other tools follow the same open standards.

Four key concepts will come up every day: images, containers, Dockerfiles, and registries.

First, an image. An image is a read-only template that contains everything needed to run an application: the code, the runtime, the libraries, and the settings. Think of it as a recipe, or, if you're a programmer, as a class.

Second, a container. A container is a running instance of an image. If the image is the recipe, the container is the dish you actually cooked. Or, in programming terms, if the image is the class, the container is the object. And just as you can create many objects from one class, you can run many containers from the same image.

Third, a Dockerfile. This is a simple text file with step-by-step instructions for building an image. A typical one for a small Python web application, read out in plain words, goes like this.

The first line says: FROM python, version three point twelve, slim. This means: start from an existing image that already has Python installed. We don't build everything from scratch; we build on top of others' work.

The next line says: WORKDIR slash app. This sets the folder inside the container where our application will live.

Then: COPY requirements dot txt, and RUN pip install. This copies the list of libraries our app needs and installs them.

Then: COPY the rest of the code into the container.

And finally: CMD python app dot py. This is the command that runs when the container starts.

That's it. Six short lines, and anyone with Docker can rebuild exactly the same environment.

One important detail: each instruction in a Dockerfile creates a layer, and Docker caches these layers. It's also the reason we copy and install the requirements before copying the rest of the code. Our code changes often, but our list of libraries changes rarely. With this order, when we edit the code and rebuild, Docker reuses the cached layer with all the installed libraries, and the build takes seconds instead of minutes.

Fourth, a registry. A registry is a place to store and share images, similar to how GitHub stores code. The most popular public one is Docker Hub, where you can find official images for Python, Node.js, PostgreSQL, Nginx, and thousands of other tools. Companies often run private registries for their own images.

A handful of basic commands ties these pieces together. You'll practice all of these later today, so for now, just get familiar with them.

docker build turns a Dockerfile into an image. We usually add a name, or tag, so we can refer to it later.

docker run creates and starts a container from an image. For example, "docker run nginx" downloads the official Nginx web server image, if you don't have it yet, and starts it.

docker ps lists the containers that are currently running.

docker stop stops a running container, and docker rm removes it.

And docker images lists the images stored on your machine.

There are two more ideas you'll need almost immediately: ports and volumes.

By default, a container is isolated, including its network. If your web app inside the container listens on port five thousand, your browser can't reach it until you connect a port on your machine to that port in the container. That's called port mapping. With the dash p option, you can say, for example, "connect port eight thousand on my laptop to port five thousand in the container."

Volumes are about data. Containers are designed to be disposable: you can delete one and start a fresh one at any time. But that means any data saved inside the container disappears when it's removed. For things that must survive, like a database's files, we use volumes, which store data outside the container. A good rule to remember: treat containers as temporary, and keep important data in volumes.

Real applications usually need more than one container. A typical web app might need the application itself, a database, and perhaps a cache. Starting them one by one with long commands quickly becomes painful. That's where Docker Compose comes in. With one configuration file, usually named compose dot yaml, you describe all your services, their ports, volumes, and how they connect. Then a single command, docker compose up, starts the whole system. For local development, this is incredibly convenient: a new team member can clone the project, run one command, and have everything working in minutes.

And when you need to run hundreds or thousands of containers across many servers in production, you'll eventually hear about Kubernetes, a system that automatically schedules, scales, and restarts containers. That's a topic for another day, but it's good to know that everything you learn today is the foundation for it.

Why have containers caught on so fast?

Consistency: the same image runs the same way everywhere. Speed: containers start in seconds. Efficiency: they use far fewer resources than virtual machines, so you can run many more on the same hardware. Isolation: each application has its own dependencies, so two apps needing different versions of the same library can live happily side by side. And easier onboarding and deployment, because the environment is defined in code, not in someone's memory.

Containers do come with a few things to watch out for. Because containers share the host's kernel, isolation is weaker than with virtual machines, so security still matters. Use official or trusted base images, keep them updated, and avoid running applications as the root user inside containers. Also, never put passwords or API keys directly into a Dockerfile, because anyone with the image can read them. And keep your images small, starting from slim base images, because smaller images build faster, download faster, and have fewer potential vulnerabilities.

Two small habits will also save you trouble. First, use a file called dot dockerignore, which works like dot gitignore, to keep things like local logs, test data, and secret files out of your image. Second, be careful with the tag "latest." It sounds safe, but it simply means "whatever version was published most recently," so the same Dockerfile can quietly build a different image next month. Pinning a specific version, like Python three point twelve, makes your builds predictable, and predictability is the whole reason we use containers in the first place.

A quick recap of the key ideas from this introduction.

Containers package an application with everything it needs, so it runs the same way everywhere. They're lighter and faster than virtual machines because they share the host's kernel. Docker makes containers easy to use. An image is the template, a container is a running instance, a Dockerfile is the recipe for building an image, and a registry is where images are shared. Ports connect containers to the outside world, volumes keep data safe, and Docker Compose runs multi-container applications with a single command.

Now it's time to stop listening and start doing. {{ argument_hands_on_activity_instructions }}

Don't worry about making mistakes. Containers are disposable, so if something breaks, you can simply delete it and start again. That's one of the best things about them.

Before you dive in, is there anything I should clear up first?
