## Reinforcement Learning for Graph Optimization in Public Transport Systems

This repository contains our contribution to a research project at the Laboratory of Information, Networking and Communication Sciences that aims to develop methods to optimize public transportation networks, with special regards to the least accessible nodes in the network. 

Accessibility is a graph-theoretical metric that measures how well a certain place (aka node) is connected to the surrounding urban area (aka the rest of the transportation graph). The design of public transit (bus, metro, train lines and frequencies) strongly impacts accessibility and is often the cause of spatial inequality between city centres and suburbs. We use Reinforcement Learning to determine the nodes to be added to the network to maximize a certain minimum accessibility metric.

As such optimization is very costly to perform on large networks (such as large urban areas), 
It is desirable to train models (Graph Neural Networks) on several cities and use them in corresponding clusters of cities (eg. urban transport systems with similar characteristics). 


In the repository:

•	Reinforcement_Learning_for_Graph_Optimization.pdf: a detailed report on the theoretical background and our contribution 

•	Nx edge generator.ipynb: a simple demo algorithm that generates edges with different constraints to simulate adding new bus lines to a transport network for example

•	Graph_Opt: a graph optimization framework proposed by Hanjun Dai et al. with several contributions from our part 
