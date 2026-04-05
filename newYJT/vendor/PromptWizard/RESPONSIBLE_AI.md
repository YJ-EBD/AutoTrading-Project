### PromptWizard: Responsible AI FAQ 

- What is PromptWizard? 

    PromptWizard is a novel framework for prompt optimization that supports to tune a good prompt for a given task and dataset, so that LLMs’ output/accuracy can be optimized. PromptWizard is solely designed for research settings, and its testing has only been carried out in such environments. It should not be used in downstream applications without additional analysis and mitigation to address potential harm or bias in the proposed application. Please refer to the paper - [PromptWizard: Task-Aware Agent-driven Prompt Optimization Framework (arxiv.org)](https://arxiv.org/abs/2405.18369)-for more details. 

- What can PromptWizard do? 

    PromptWizard framework is an AI-based framework that internally uses LLM to find the optimal prompt for a given task. It takes as input task description, dataset format & few training examples, hyperparameter configurations and outputs an optimized prompt for the given LLM and task intent. 
    Unlike existing approaches, PromptWizard optimizes both prompt instructions and in-context examples, maximizing the LLM performance. It iteratively refines prompts by mutating instructions using and incorporating negative examples. It further enhances both instructions and examples with the aid of a critic provided by LLM on a candidate prompt.  
    New synthetic instructions and examples are generated with detailed reasoning steps using LLM. 

- What is/are PromptWizard’s intended use(s)? 

    Please note that PromptWizard is an open-source framework under active development and intended for use for research purposes. It should not be used in any downstream applications without additional detailed evaluation of robustness, safety issues and assessment of any potential harm or bias in the proposed application. For all GenAI applications, prompt design and tuning are a tedious, skilful and laborious tasks. PromptWizard’s intended use is to design and optimize the prompt along with the few shot examples for a given task/domain and dataset. This well crafted prompt would enable the LLM to provide more accurate and high quality answer. We have also integrated Azure AI Content Safety service, to avoid/slow-down malicious uses. 

- How was PromptWizard evaluated? What metrics are used to measure performance? 

    PromptWizard framework is generic enough to work on any domain/dataset/task. However, we have evaluated the performance of PromptWizard across 35 tasks on 8 datasets. More details can be found [PromptWizard: Task-Aware Agent-driven Prompt Optimization Framework (arxiv.org)](https://arxiv.org/abs/2405.18369) 

    The opensource datasets used for evaluation include
    - Medical challenges ([MedQA](https://github.com/jind11/MedQA), [PubMedQA](https://pubmedqa.github.io/)) 
    - Commonsense reasoning ([CSQA](https://amritasaha1812.github.io/CSQA/), [SQA](https://www.microsoft.com/en-in/download/details.aspx?id=54253))
    - Math reasoning problems ([GSM8k](https://huggingface.co/datasets/openai/gsm8k))
    - Hate speech classification ([Ethos](https://link.springer.com/article/10.1007/s40747-021-00608-2)),  
    - Complex domain-specific tasks ([MMLU](https://huggingface.co/datasets/cais/mmlu) 6 medical tasks, [Big-Bench-Hard-23](https://huggingface.co/datasets/maveriq/bigbenchhard)) 

    Additionally, the team has also conducted “red team” analysis to evaluate if PromptWizard optimizes harmful intent. With appropriate Azure content moderation deployed in the pipeline on the input to PromptWizard and output from PromptWizard, it didn’t optimize prompts for harmful intent. Please refer to the details for Azure content moderation [here](https://learn.microsoft.com/en-us/azure/ai-services/content-moderator/overview). 

- What are the limitations of PromptWizard? How can users minimize the impact of PromptWizard’s limitations when using the system? 

    - The framework is evaluated primarily on English languages tasks as described in earlier section. The framework is not yet evaluated for multilingual settings. 
    - The framework generates synthetic examples for few-shot learning based on task description. User is required to validate the correctness and diversity of generated synthetic examples. 
    - PromptWizard utilizes existing LLMs and does not train a new model. Hence, it inherits the capabilities and limitations of its base model, as well as common limitations among other large language models or limitations caused by its training process. Hence, we suggest using the appropriate base LLM suitable for your use-cases to work with PromptWizard. 

- What operational factors and settings allow for effective and responsible use of PromptWizard? 

  - Input considerations: Better performance with PromptWizard can be achieved by specifying the input components like task and intent as clearly and concisely as possible. 
  - Human involvement: PromptWizard optimizes the prompt with prompt instruction and a few shot examples for the given intent and task.  We suggest human oversight to review the optimized prompts before those are executed with LLMs. 
  - LLMs: Users can choose the LLM that is optimized for responsible use. The default LLM is GPT-4 which inherits the existing RAI mechanisms and filters from the LLM provider. Caching is enabled by default to increase reliability and control cost. We encourage developers to review [OpenAI’s Usage policies](https://openai.com/policies/usage-policies/) and [Azure OpenAI’s Code of Conduct](https://learn.microsoft.com/en-us/legal/cognitive-services/openai/code-of-conduct) when using GPT-4. 
  - Content Safety: We have integrated [Azure AI Content Safety](https://learn.microsoft.com/en-us/azure/ai-services/content-safety/overview) service for content moderation. We suggest to deploy PromptWizard with such content safety system in the pipeline.  