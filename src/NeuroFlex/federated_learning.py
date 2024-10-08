import jax
import jax.numpy as jnp
import flax.linen as nn
from flax.training import train_state
import optax
from typing import List, Dict, Any, Callable
import logging

class FederatedLearning:
    def __init__(self, model: nn.Module, num_clients: int):
        self.model = model
        self.num_clients = num_clients
        self.client_states: List[train_state.TrainState] = []
        logging.info(f"Initialized Federated Learning with {num_clients} clients")

    def initialize_clients(self, rng: jax.random.PRNGKey, dummy_input: jnp.ndarray, learning_rate: float):
        """Initialize client models with the same architecture but different random weights."""
        for i in range(self.num_clients):
            client_rng = jax.random.fold_in(rng, i)
            client_state = create_train_state(client_rng, self.model, dummy_input, learning_rate)
            self.client_states.append(client_state)
        logging.info("Initialized all client models")

    def train_round(self, client_data: List[Dict[str, jnp.ndarray]],
                    global_round: int,
                    local_epochs: int = 1):
        """Perform one round of federated learning."""
        updated_states = []
        for i, (state, data) in enumerate(zip(self.client_states, client_data)):
            updated_state = self.train_client(state, data, local_epochs)
            updated_states.append(updated_state)
            logging.info(f"Trained client {i+1}/{self.num_clients} in round {global_round}")

        # Aggregate model updates
        global_params = self.federated_averaging([state.params for state in updated_states])

        # Update all clients with the new global model
        self.client_states = [state.replace(params=global_params) for state in self.client_states]
        logging.info(f"Completed federated learning round {global_round}")

    def train_client(self, state: train_state.TrainState,
                     data: Dict[str, jnp.ndarray],
                     epochs: int) -> train_state.TrainState:
        """Train a single client for a number of local epochs."""
        @jax.jit
        def train_step(state, batch):
            def loss_fn(params):
                logits = self.model.apply({'params': params}, batch['x'])
                return optax.softmax_cross_entropy_with_integer_labels(logits, batch['y']).mean()

            loss, grads = jax.value_and_grad(loss_fn)(state.params)
            state = state.apply_gradients(grads=grads)
            return state, loss

        for epoch in range(epochs):
            state, loss = train_step(state, data)

        return state

    def federated_averaging(self, params_list: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate model parameters using federated averaging."""
        return jax.tree_map(lambda *x: jnp.mean(jnp.array(x), axis=0), *params_list)

    def evaluate_global_model(self, test_data: Dict[str, jnp.ndarray]) -> float:
        """Evaluate the global model on test data."""
        @jax.jit
        def evaluate(params, batch):
            logits = self.model.apply({'params': params}, batch['x'])
            predicted_class = jnp.argmax(logits, axis=-1)
            return jnp.mean(predicted_class == batch['y'])

        global_params = self.client_states[0].params  # All clients have the same global model
        accuracy = evaluate(global_params, test_data)
        logging.info(f"Global model accuracy: {accuracy:.4f}")
        return accuracy

def create_train_state(rng: jax.random.PRNGKey,
                       model: nn.Module,
                       dummy_input: jnp.ndarray,
                       learning_rate: float) -> train_state.TrainState:
    """Create and initialize the model state."""
    params = model.init(rng, dummy_input)['params']
    tx = optax.adam(learning_rate)
    return train_state.TrainState.create(apply_fn=model.apply, params=params, tx=tx)

def secure_aggregation(params_list: List[Dict[str, Any]],
                       encryption_fn: Callable[[Dict[str, Any]], Dict[str, Any]],
                       decryption_fn: Callable[[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
    """Perform secure aggregation of model parameters."""
    # Encrypt client parameters
    encrypted_params = [encryption_fn(params) for params in params_list]

    # Aggregate encrypted parameters
    aggregated_encrypted = jax.tree_map(lambda *x: jnp.sum(jnp.array(x), axis=0), *encrypted_params)

    # Decrypt aggregated parameters
    decrypted_params = decryption_fn(aggregated_encrypted)

    # Compute average
    num_clients = len(params_list)
    averaged_params = jax.tree_map(lambda x: x / num_clients, decrypted_params)

    return averaged_params

# Example usage
if __name__ == "__main__":
    # Initialize your model here
    model = nn.Dense(features=10)
    num_clients = 5
    federated_system = FederatedLearning(model, num_clients)

    # Initialize clients
    rng = jax.random.PRNGKey(0)
    dummy_input = jnp.ones((1, 28, 28, 1))  # Example for MNIST
    federated_system.initialize_clients(rng, dummy_input, learning_rate=0.001)

    # Simulate federated learning rounds
    for round in range(10):
        # In practice, you would distribute this data to actual clients
        client_data = [{'x': jnp.ones((32, 28, 28, 1)), 'y': jnp.zeros(32, dtype=jnp.int32)} for _ in range(num_clients)]
        federated_system.train_round(client_data, round)

    # Evaluate the global model
    test_data = {'x': jnp.ones((100, 28, 28, 1)), 'y': jnp.zeros(100, dtype=jnp.int32)}
    final_accuracy = federated_system.evaluate_global_model(test_data)
    print(f"Final global model accuracy: {final_accuracy:.4f}")
