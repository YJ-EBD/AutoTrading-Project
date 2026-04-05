# BBH Datasets
# informal_to_formal
task_description = 'In this task, you will be given a sentence in an informal style. Your job is to rewrite the sentence in a formal style.'
base_instruction = 'For each given sentence, provide a formal paraphrase.'
answer_format = 'For each input sentence, present the reasoning followed by the format paraphrased sentence.'

#letters_list
task_description = 'In this task, you will be given a single word as input. Your job is to produce the output by adding a space between each character pair in the word.'
base_instruction = 'For each given word, insert a space between each character pair in the word.'
answer_format = 'For each input word, ouput only the space seperated characters.'

#negation
task_description = 'For each input, write a sentence that expresses the exact opposite meaning of the input.'
base_instruction = 'For each given sentence, provide a new sentence that conveys the exact opposite meaning by using "not" in the input sentence, keeping the rest of the sentence unchanged.'
answer_format = "For each input sentence, negate the meaning by adding 'not' to the input sentence."

#orthography_starts_with
task_description = 'For each input, output all the words in the sentence that begin with the character in brackets at the end of the sentence.'
base_instruction = 'Output words with space separated that begin with the character in brackets at the end of the following sentence='
answer_format = 'For each input sentence, present the reasoning followed by space seperated words.'

#rhymes
task_description = 'In this task, you will be given a single word as input. Your job is to produce list of comma sperated words that rhymes with the input word.'
base_instruction = 'For each given word, provide a list of words that rhyme with the input word='
answer_format = 'For each input word, present the reasoning followed by the list of rhyming word.'

#second_word_letter
task_description = 'Extract the second letter from the input word.'
base_instruction = 'Output the second letter. Think step by step to arrive at the solution.'
answer_format = 'For each input word, present the reasoning followed by the extracted letter (only single letter).'

#sentence_similarity
task_description = "Each input consists of two sentences (Sentence 1 and Sentence 2). Rate on a scale of 0 to 5 whether those sentences are paraphrases of each other, and also give a brief textual description of the rating (0 - definitely not, 2 - possibly, 3 - probably, 4 - almost perfectly and 5 - perfectly). Use \" - \" to separate them"
base_instruction = """Rate the similarity of each pair of sentences according to the following scale: 

0 - Definitely not : The sentences are completely unrelated in meaning.
1 - Probably not : The sentences have minor or superficial similarities but differ significantly in meaning.
2 - Possibly : The sentences share some elements of meaning but are not strong paraphrases.
3 - Probably : The sentences convey similar meanings but have some differences.
4 - Almost perfectly : The sentences are very similar with only minor differences.
5 - Perfectly :The sentences are nearly identical in meaning."""
answer_format = 'Provide your rating and brief textual description for each pair of sentences from the 6 options. (0 - Definitely not, 1 - Probably not, 2 - Possibly, 3 - Probably, 4 - Almost perfectly, 5 - Perfectly)'

#sum
task_description = 'For each input, write the sum of the two numbers that appears there.'
base_instruction = 'Output the sum of the following two numbers='
answer_format = 'For each pair of numbers, present the reasoning followed by the sum.'

#synonyms
task_description = 'You will be given a word as input and need to output a word that is semantically similar.'
base_instruction = 'Output a word that is semantically similar to the input word='
answer_format = 'For each input word, present the reasoning followed by the synonym.'

#taxonomy_animal
task_description = 'In this task, you will be given a list of words. Your job is to identify and list all the animals from the given set of words.'
base_instruction = 'For each given list of words, provide a new list containing only the animals.'
answer_format = 'For each list of words, output the list of animals.'

#auto_categorization
task_description = 'Find the best categorization for the given set of words as input.'
base_instruction = 'Output the best categorization for the following set of words='
answer_format = 'For each set of words, present the reasoning followed by the best categorization.'

#object_counting
task_description = 'Find the number of objects in the given input.'
base_instruction = 'Output the number of objects in the following input='
answer_format = 'For each input, present the reasoning followed by the number of objects.'

#odd_one_out
task_description = 'Given the below list of words, find the odd one out'
base_instruction = 'Output the word that does not belong to the group of words='
answer_format = 'For each group of words, present the reasoning followed by the odd one out.'

#word_sorting
task_description = 'In this task, you will be given a set of words. Your job is to sort the words based on the first character of each word in alphabetical order.'
base_instruction = 'For each given set of words, provide a sorted list of the words based on the first character of each word.'
answer_format = 'For each input, list of sorted words based on the first character of each word.'

#word_unscrambling
task_description = 'In this task output all possible meaningful words that can be formed by rearranging all the letters of the given word. Each character must be used exactly once and the words must be valid.'
base_instruction = 'Output comma seperated words of same length as input word.'
answer_format = 'Output the all possible meaningful words comma seperated that can formed by rearranging the letters of the given word.'

#antonyms
task_description = 'In this task, you will be given a single word as input. Your job is to produce a word that has the exact opposite meaning (an antonym) to the input word.'
base_instruction = 'For each given word, provide a word that is an antonym (has the exact opposite meaning).'
answer_format = 'For each input word, output only a single word.'

#cause_and_effect
task_description = 'Find the cause in the following cause and effect pair. Each input consists of two sentences, where one is the cause and the other is the outcome.'
base_instruction = 'Output the cause in the following cause and effect pair='
answer_format = 'For each pair of sentences, present the reasoning followed by the cause.'

#common_concept
task_description = 'In this task, you will be given a list of objects. Your job is to identify and describe a common characteristic that links all the objects in the list.'
base_instruction = 'The instruction is to ”involve” the objects mentioned in the input.'
answer_format = 'For each list of objects, output the common concept by "involving" the objects mentioned.'