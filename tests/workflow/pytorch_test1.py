# Adapted from https://pytorch.org/tutorials/beginner/pytorch_with_examples.html#
# Author: Justin Johnson


def main(datapoints: int, iterations: int, learning_rate: float):
    import torch

    torch.manual_seed(0)
    import math

    # Create Tensors to hold input and outputs.
    x = torch.linspace(-math.pi, math.pi, datapoints)
    y = torch.sin(x)

    # Prepare the input tensor (x, x^2, x^3).
    p = torch.tensor([1, 2, 3])
    xx = x.unsqueeze(-1).pow(p)

    # Use the nn package to define our model and loss function.
    model = torch.nn.Sequential(torch.nn.Linear(3, 1), torch.nn.Flatten(0, 1))
    loss_fn = torch.nn.MSELoss(reduction="sum")

    # Use the optim package to define an Optimizer that will update the weights of
    # the model for us. Here we will use RMSprop; the optim package contains many other
    # optimization algorithms. The first argument to the RMSprop constructor tells the
    # optimizer which Tensors it should update.
    optimizer = torch.optim.RMSprop(model.parameters(), lr=learning_rate)
    for t in range(iterations):
        # Forward pass: compute predicted y by passing x to the model.
        y_pred = model(xx)

        # Compute and print loss.
        loss = loss_fn(y_pred, y)
        if t % 100 == 99:
            print(t, loss.item())

        # Before the backward pass, use the optimizer object to zero all of the
        # gradients for the variables it will update (which are the learnable
        # weights of the model). This is because by default, gradients are
        # accumulated in buffers( i.e, not overwritten) whenever .backward()
        # is called. Checkout docs of torch.autograd.backward for more details.
        optimizer.zero_grad()

        # Backward pass: compute gradient of the loss with respect to model
        # parameters
        loss.backward()

        # Calling the step function on an Optimizer makes an update to its
        # parameters
        optimizer.step()

    linear_layer = model[0]
    result = f"Result: y = {linear_layer.bias.item()} + {linear_layer.weight[:, 0].item()} x + {linear_layer.weight[:, 1].item()} x^2 + {linear_layer.weight[:, 2].item()} x^3"
    return result


if __name__ == "__main__":
    result = main(datapoints=2000, iterations=2000, learning_rate=1e-3)
    print(result)

if __name__ == "transformer":  # Seamless
    result = main(
        datapoints=datapoints, iterations=iterations, learning_rate=learning_rate
    )
