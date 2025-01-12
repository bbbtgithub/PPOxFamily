"""
PyTorch implementation of Language Model Environment.

There are two main components in this documentation:
- We use GPT-2 as the base language model and construct an environment.
- We make a demonstration of this environment and users can type prompts in the command line to interact with the language model.
"""
#########################################################
#lm_env2.py与lm_env.py的区别在于lm_env2.py中不使用用户交互环境，而是直接用自动生成的query进行交互
#用自动生成的query进行交互
#用自动生成的query进行交互
#用自动生成的query进行交互
#########################################################
import torch
import gym
from typing import Callable, Optional, Dict, Tuple
# For more information about GPT2, please refer to this doc: <link https://huggingface.co/transformers/v3.0.2/model_doc/gpt2.html#gpt2lmheadmodel link>.
from transformers import GPT2Tokenizer, GPT2LMHeadModel

obs_dim = 8
def calculate_perplexity(model: GPT2LMHeadModel, query: torch.Tensor, response: torch.Tensor) -> float:
    """
    **Overview:**
        Calculate the perplexity of the response given a language model, query token ids and response token ids. \
        In essence, the perplexity is the exponential result of cross entropy loss, which can reflect the quality of \
        the generation to some extent.
    **Arguments:**
        - model: The language model to calculate perplexity.
        - query: The token ids for query.
        - response: The token ids for response.
    """
    # Concatenate the query and response.
    total_input = torch.cat([query, response], dim=0)
    # Calculate the logits given the token ids.
    logits = model(total_input, return_dict=True).logits

    # Shift the output logits and input ids to match their dimension.
    # For the i-th shifted logits, it corresponds to the i-th shifted label.
    start = query.shape[0]
    shifted_logits = logits[start:-1, :]
    shifted_labels = total_input[start+1:]

    # Use cross entropy loss to calculate the perplexity.
    loss_fct = torch.nn.CrossEntropyLoss()
    loss = loss_fct(shifted_logits, shifted_labels)
    ppl = torch.exp(loss).item()
    return ppl


class TextHistory:
    """
    **Overview:**
        The TextHistory class keeps track of the history of an interaction between the language model and the environment.
    """

    def __init__(self, text: str, tokens: Optional[torch.Tensor]):
        """
        **Overview:**
            Initialize TextHistory.
        **Arguments:**
            - text: The text of the first segment.
            - tokens: The tokens of the first segment.
        """
        
        # Record the total text generated by both user and language model.
        self.text = text
        # Record the ranges of text for each reply.
        self.text_spans = []
        # Record the tokenized total text generated by both user and language model.
        if len(text) == 0:
            self.text = ""
            self.tokens = torch.tensor([], dtype=torch.int64)
            return
        self.tokens = tokens
        # This flag shows whether this record is finished.
        self.completed = False

        self.append_segment(text, tokens)

    # delimiter
    def append_segment(self, text: str, tokens: torch.Tensor) -> None:
        """
        **Overview:**
            Append a new segment to the history.
        **Arguments:**
            - text: The text of the new segment.
            - tokens: The tokens of the new segment.
        """
        # If the text is empty, raise Error.
        if len(text) == 0 or len(tokens) == 0:
            raise ValueError("Can't append empty text or token list to history.")

        # Add the new text to ``self.text``
        original_text_length = len(self.text)
        self.text += text
        # Update the range of this new text segment.
        self.text_spans.append((original_text_length, len(self.text)))
        # Add the new tokens to ``self.tokens``.
        self.tokens = torch.cat((self.tokens, tokens))
        if len(self.tokens) > obs_dim:#会出现异常索引的问题，感觉是token太长导致的
            self.tokens = self.tokens[-obs_dim:]

    # delimiter
    @property
    def last_text_segment(self) -> str:
        """
        **Overview:**
            Get the last text segment.
        """
        start, end = self.text_spans[-1]
        return self.text[start:end]


    def to_obs(self) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        **Overview:**
            Convert the history object into an observation tensor and the corresponding mask. \
            The observation tensor will be padded to a fixed length (obs_dim). \
            For ids generated by user, the mask value is 1; for ids generated by language model, the mask value is 2; for padding ids, the mask value is 0.
        """
        # Pad the observation to obs_dim.
        #obs = self.tokens
        #如果 self.tokens 是 None，初始化为长度为 0 的张量
        obs = self.tokens if self.tokens is not None else torch.tensor([], dtype=torch.int64)
        
        if len(obs) < obs_dim:
            obs = torch.nn.functional.pad(obs, (0, obs_dim-len(obs)))
        
        obs = obs.float() #其实应该是整形，但是如果转换成.long()对应用LongTensor,总是报错:
        """RuntimeError: mat1 and mat2 must have the same dtype, but got Long and Float"""
        
        # Generate corresponding mask.
        mask = torch.zeros_like(obs)
        
        if self.text_spans is None:print("self.text_spans is None")
        else:
            for i in range(len(self.text_spans)):
                sli = self.text_spans[i]
                # For ids generated for users, the mask value is 1.
                if i % 2 == 0:
                    mask[sli[0]: sli[1]] = 1
                # For ids generated by language model, the mask value is 2.
                else:
                    mask[sli[0]: sli[1]] = 2
                    
            return obs, mask


# delimiter
class TextEnvironment(gym.Env):
    """
    **Overview:**
        The TextEnvironment enables interaction of a LLM with an environment.
    """

    def __init__(self, model: GPT2LMHeadModel, tokenizer: GPT2Tokenizer, reward_fn: Callable,
                 max_turns: int = 4, generation_kwargs: Optional[Dict] = None):
        """
        **Overview:**
            Initialize the TextEnvironment.

        **Arguments:**
            - model: The model to use for generation.
            - tokenizer: The tokenizer to use for generation.
            - reward_fn: A callable function that takes a string and returns a reward.
            - max_turns: The maximum number of turns to allow.
            - generation_kwargs: A dictionary of keyword arguments to pass to the model's generate method.
        """
        # Initialize the arguments.
        self.model = model
        self.tokenizer = tokenizer
        self.reward_fn = reward_fn
        self.max_turns = max_turns

        # Prepare the arguments for text generation.
        if generation_kwargs is None:
            self.generation_kwargs = dict()
        else:
            self.generation_kwargs = generation_kwargs

        # Count the times of ``self.step()``
        self.turn = 0
        # Preserve the history of interactions.
        self.history = TextHistory("", None)
        # Determine the device of running the model (cpu or cuda).
        self.current_device = self.model.device

        # Define the action-space, reward-space and observation-space.
        # The action space is a sentence (string type).
        self._action_space = gym.spaces.Text(max_length=obs_dim)
        # In this demo, we use the negative perplexity as reward, whose range is (-inf, 0).
        self._reward_space = gym.spaces.Box(-float('inf'), 0)
        # The observation is the history query and response, whose shape is obs_dim.
        # If the total length of history < obs_dim, it will be padded. Detailed implementation is shown in ``TextHistory.to_obs``.
        # For each element of the observation, the value range is [0, vcab_size).
        self._observation_space = gym.spaces.Box(0, tokenizer.vocab_size, [obs_dim])

    # delimiter
    def reset(self):
        """
        **Overview:**
            Reset the environment.
        """
        # Reset the history and the counter of step number.
        self.history = TextHistory("", None)
        self.turn = 0
        obs, mask = self.history.to_obs()
        return obs, mask

    # delimiter
    def generate(self) -> torch.Tensor:
        """
        **Overview:**
            Generate responses for a history.
        """
        # The input of model is all the interaction histories.
        query_tensors = self.history.tokens
        # Generate reply.
        response_tensors = self._generate(query_tensors)
        # Decode the reply into string format.
        response_texts = self.tokenizer.decode(response_tensors)
        # Add the new generated reply to ``self.history``
        self.history.append_segment(response_texts, response_tensors)

        return response_tensors

    # delimiter
    def step(self, query: str) -> Tuple[torch.Tensor, float, bool, Dict]:
        """
        **Overview:**
            The step function of the language model environment.
        """
        query = str(query)
        #确保是字符串
        #print("query:",query)
        # The history is not initialized. Create a new history.
        if self.history.tokens is None:

            query_tokens = self.tokenizer(query, return_tensors="pt").input_ids[0].to(self.current_device)
            self.history = TextHistory(query, query_tokens)
        # The history is already initialized. Append to the original history.
        else:
            query_tokens = self.tokenizer(query, return_tensors="pt").input_ids[0].to(self.current_device)
            self.history.append_segment(query, query_tokens)
        # Generate response.
        response_tokens = self.generate()
        # Calculate the reward function.
        rew = self.reward_fn(self.model, query_tokens, response_tokens)
        # Check whether the environment is finished.
        self.turn += 1
        self.history.completed = self.turn >= self.max_turns
        obs, mask = self.history.to_obs()
        return obs, rew, self.history.completed, {"mask": mask}

    # delimiter
    def _generate(self, query_tensors: torch.Tensor) -> torch.Tensor:
        """
        **Overview:**
            Generate responses for a list of query tensors.
        **Arguments:**
            - query_tensors (torch.Tensor): A list of query tensors to generate responses for.
        """
        # Add the batch_size dimension to the original input. Shape: [T, N] -> [1, T, N]
        query_tensors = query_tensors.unsqueeze(0)
        # Generate the corresponding mask tensor.
        batch_mask = torch.ones_like(query_tensors)
        inputs = {"input_ids": query_tensors, "attention_mask": batch_mask}

        # Call the ``generate()`` API of GPT-2.
        generation = self.model.generate(**inputs, **self.generation_kwargs,
                                         pad_token_id=self.tokenizer.eos_token_id)

        # Remove prompt from the total completed sentence.
        output = generation[0, batch_mask[0].sum():]
        return output


# delimiter
def test_env():
    """
    **Overview:**
        In this function, we test the language model environment and interact with it by typing prompts in the command line.
    """
    # Load the pretrained model and tokenizer.
    # When first call this function, the pretrained files will be automatically downloaded from <link https://huggingface.co/ link>.
    tokenizer = GPT2Tokenizer.from_pretrained('gpt2')
    tokenizer.pad_token = tokenizer.eos_token
    model = GPT2LMHeadModel.from_pretrained('gpt2')
    # For simplicity, we set the reward function to be the negative perplexity.
    reward_function = lambda lm, query, response: - calculate_perplexity(lm, query, response)
    # Arguments for text generation.
    generation_kwargs = {
        # The maximum number of tokens can be generated by language model is 20.
        'max_new_tokens': 20,
        # Use nondeterministic method to sample generated results each time.
        'do_sample': True,
        # The temperature of softmax function for sampling.
        'temperature': 0.7,
        # Penalize the language model to generate repeated words.
        'repetition_penalty': 2.0
    }
    # Initialize the environment.
    env = TextEnvironment(model=model, tokenizer=tokenizer, max_turns=3, reward_fn=reward_function,
                          generation_kwargs=generation_kwargs)
    env.reset()
    #用自动生成的query进行交互
    for _ in range(env.max_turns):
        obs, reward, done, info = env.step("Auto-generated query here")  # 直接调用环境的 step 方法
        print("Response (Reward={:.2f}):{}".format(reward, env.history.last_text_segment))
        if done:
            break
    """
    # Interaction loop.
    while True:
        # User input the question.
        q = input("Please type in your question:")
        # The env step once.
        obs, reward, done, info = env.step(q)
        # Print the response and reward.
        print("Response (Reward={:.2f}):{}".format(reward, env.history.last_text_segment))
        # If the environment is done, break the interaction loop.
        if done:
            break
    """

if __name__ == '__main__':
    test_env()
