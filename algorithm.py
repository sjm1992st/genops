import theano
import theano.tensor as T
from theano.tensor.shared_randomstreams import RandomStreams
import numpy as np
import time
from abc import ABCMeta
import sys

def logOK(text):
	print time.strftime('%H:%M:%S') + ": " + '\033[92m' + text + '\033[0m'

def logERROR(text):
	print time.strftime('%H:%M:%S') + ": " +  '\033[91m' + text + '\033[0m'

def log(text):
	print time.strftime('%H:%M:%S') + ": " +  text

class EA(object):
	__metaclass__ = ABCMeta

	def __init__(self):
		self.rng = RandomStreams()

		self.entity_mutate_rate = 0.1
		self.bit_mutate_rate = 0.05
		self.crossover_rate = 0.7
	
	def initialize_random_population(self):
		return np.random.randint(2, size = (1000, 1000)).astype(theano.config.floatX) # 1000 entities, 1000 bits

class SimpleEA(EA):
	def __init__(self, fitnessFunction):
		"""
		Initialize a simple EA algorithm class.
		Creating the SimpleEA object compiles the needed Theano functions.
		
		:param fitnessFunction: The fitness function that takes a matrix of entities and and outputs a vector of fitness values for the ids given in `changes`.
		:param selectionFunction: The selection function that takes a matrix of entities and a vector of fitnesses and outputs a matrix of entities.
		"""
		super(SimpleEA, self).__init__()

		self.fitness = fitnessFunction
	
	def cross(self, entities):
		n, m = entities.shape
		pop = T.reshape(entities, (2, n*m/2))
		xpoints = self.rng.random_integers(size = (n / 2,), low = 0, high = m-1)
		
		def choice_vector(xpoint, nbits):
			return T.concatenate([T.zeros((xpoint,), dtype='uint8'), T.ones((nbits-xpoint,), dtype='uint8')])
		
		values, updates = theano.map(fn=choice_vector, sequences=[xpoints], non_sequences=[m], name='choice_vector_building')
		
		a = T.reshape(values, (n*m/2,))
		pop = T.concatenate([T.choose(a, pop), T.choose(1-a, pop)])
		pop = T.reshape(pop, (n,m))
		return pop

	def tournament_selection(self, entities, fitness, rng):
		"""
		TODO:
		* Contains 1 HostFromGpu (argmax)
		"""
		# Create random integers
		r = rng.random_integers(size = (entities.shape[0]*2,), low = 0, high = entities.shape[0]-1)

		# Take randomly matched entities' fitnesses and reshape
		chosen_f = fitness[r].reshape((2, entities.shape[0]))

		# Take winner IDs (binary)
		winner_ids = T.argmax(chosen_f, axis=0)

		# Compute entity IDs
		entity_ids = r[T.arange(entities.shape[0])+(winner_ids*entities.shape[0])]

		return entities[entity_ids]

	def fast_mutation(self, entities):
		"""
		Randomly flips bits in the population matrix.

		TODO:
		* Contains 1 HostFromGpu
		* Contains 1 GpuFromHost
		"""
		p = self.bit_mutate_rate * self.entity_mutate_rate
		r = self.rng.choice(size = entities.shape, p = [1-p, p])

		non_zero_indices = r.nonzero()

		to_be_changed = entities[non_zero_indices]
		changed_to = 1 - to_be_changed

		entities = T.set_subtensor(to_be_changed, changed_to)

		return entities
		
	def run(self, generations = 50):
		log("Compiling...")
		
		E = self.initialize_random_population()
		F = np.zeros((E.shape[0]), dtype=theano.config.floatX)

		# Change these to shared variables
		E = theano.shared(E)
		F = theano.shared(F)

		# Create graphs
		fitness_t = self.fitness(E)
		select_t = self.tournament_selection(E, F, self.rng)
		mutate_t = self.fast_mutation(E)
		crossover_t = self.cross(E)

		# Compile functions
		fitness = theano.function([], [], updates = [(F, fitness_t)])
		select = theano.function([], [], updates = [(E, select_t)])
		mutate = theano.function([], [], updates = [(E, mutate_t)])
		crossover = theano.function([], [], updates = [(E, crossover_t)])

		logOK("Compilation successfully completed.")
		log("Running algorithm...")

		start = time.time()

		fitness()
		
		for i in range(generations):
			select()
			crossover()
			mutate()
			
			fitness()

			if theano.config.profile:
				log("Fitness: " + str(np.max(F.get_value())))

			# Early stopping
			if np.max(F.get_value()) == 100:
				break

		end = time.time()

		if theano.config.profile:
			theano.printing.pydotprint(fitness, outfile="fitness.pdf", format="pdf")
			theano.printing.pydotprint(select, outfile="select.pdf", format="pdf")
			theano.printing.pydotprint(mutate, outfile="mutate.pdf", format="pdf")
			theano.printing.pydotprint(crossover, outfile="cross.pdf", scan_graphs = True, format="pdf")

		return E.eval(), start, end, i+1
		
if __name__ == "__main__":

	def fit(entities):
		return T.sum(entities, axis=1)

	ea = SimpleEA(fit)

	if len(sys.argv) > 1 and sys.argv[1] == "benchmark":
		times = 20
	else:
		times = 1

	total_time = 0
	total_iterations = 0

	for i in range(times):
		entities, start, end, iterations = ea.run()
		total_time += end-start
		total_iterations += iterations

	avg_time = total_time / float(times)
	avg_iterations = total_iterations / float(times)

	f = np.max(np.sum(entities, axis=1))

	logOK("Done.")
	log("Device: %s" % theano.config.device)
	log("Max fitness: %i" % f)
	log("Time taken: %.5f seconds" % avg_time)
	log("Iterations taken: %.1f" % avg_iterations)
