# Copyright 2023 The KerasNLP Authors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import io

import sentencepiece
import tensorflow as tf

from keras_nlp.backend import keras
from keras_nlp.models.deberta_v3.deberta_v3_masked_lm_preprocessor import (
    DebertaV3MaskedLMPreprocessor,
)
from keras_nlp.models.deberta_v3.deberta_v3_tokenizer import DebertaV3Tokenizer
from keras_nlp.tests.test_case import TestCase


class DebertaV3PreprocessorTest(TestCase):
    def setUp(self):
        bytes_io = io.BytesIO()
        vocab_data = tf.data.Dataset.from_tensor_slices(
            ["the quick brown fox", "the earth is round"]
        )
        sentencepiece.SentencePieceTrainer.train(
            sentence_iterator=vocab_data.as_numpy_iterator(),
            model_writer=bytes_io,
            vocab_size=12,
            model_type="WORD",
            pad_id=0,
            bos_id=1,
            eos_id=2,
            unk_id=3,
            pad_piece="[PAD]",
            bos_piece="[CLS]",
            eos_piece="[SEP]",
            unk_piece="[UNK]",
            user_defined_symbols="[MASK]",
        )
        self.proto = bytes_io.getvalue()
        self.tokenizer = DebertaV3Tokenizer(proto=self.proto)
        self.preprocessor = DebertaV3MaskedLMPreprocessor(
            tokenizer=self.tokenizer,
            # Simplify our testing by masking every available token.
            mask_selection_rate=1.0,
            mask_token_rate=1.0,
            random_token_rate=0.0,
            mask_selection_length=4,
            sequence_length=12,
        )

    def test_preprocess_strings(self):
        input_data = "the quick brown fox"

        x, y, sw = self.preprocessor(input_data)
        self.assertAllEqual(
            x["token_ids"], [1, 4, 4, 4, 4, 2, 0, 0, 0, 0, 0, 0]
        )
        self.assertAllEqual(
            x["padding_mask"], [1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0]
        )
        self.assertAllEqual(x["mask_positions"], [1, 2, 3, 4])
        self.assertAllEqual(y, [5, 10, 6, 8])
        self.assertAllEqual(sw, [1.0, 1.0, 1.0, 1.0])

    def test_preprocess_list_of_strings(self):
        input_data = ["the quick brown fox"] * 4

        x, y, sw = self.preprocessor(input_data)
        self.assertAllEqual(
            x["token_ids"], [[1, 4, 4, 4, 4, 2, 0, 0, 0, 0, 0, 0]] * 4
        )
        self.assertAllEqual(
            x["padding_mask"], [[1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0]] * 4
        )
        self.assertAllEqual(x["mask_positions"], [[1, 2, 3, 4]] * 4)
        self.assertAllEqual(y, [[5, 10, 6, 8]] * 4)
        self.assertAllEqual(sw, [[1.0, 1.0, 1.0, 1.0]] * 4)

    def test_preprocess_dataset(self):
        sentences = tf.constant(["the quick brown fox"] * 4)
        ds = tf.data.Dataset.from_tensor_slices(sentences)
        ds = ds.map(self.preprocessor)
        x, y, sw = ds.batch(4).take(1).get_single_element()
        self.assertAllEqual(
            x["token_ids"], [[1, 4, 4, 4, 4, 2, 0, 0, 0, 0, 0, 0]] * 4
        )
        self.assertAllEqual(
            x["padding_mask"], [[1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0]] * 4
        )
        self.assertAllEqual(x["mask_positions"], [[1, 2, 3, 4]] * 4)
        self.assertAllEqual(y, [[5, 10, 6, 8]] * 4)
        self.assertAllEqual(sw, [[1.0, 1.0, 1.0, 1.0]] * 4)

    def test_mask_multiple_sentences(self):
        sentence_one = tf.constant("the quick")
        sentence_two = tf.constant("brown fox")

        x, y, sw = self.preprocessor((sentence_one, sentence_two))
        self.assertAllEqual(
            x["token_ids"], [1, 4, 4, 2, 4, 4, 2, 0, 0, 0, 0, 0]
        )
        self.assertAllEqual(
            x["padding_mask"], [1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
        )
        self.assertAllEqual(x["mask_positions"], [1, 2, 4, 5])
        self.assertAllEqual(y, [5, 10, 6, 8])
        self.assertAllEqual(sw, [1.0, 1.0, 1.0, 1.0])

    def test_no_masking_zero_rate(self):
        no_mask_preprocessor = DebertaV3MaskedLMPreprocessor(
            self.preprocessor.tokenizer,
            mask_selection_rate=0.0,
            mask_selection_length=4,
            sequence_length=12,
        )
        input_data = "the quick brown fox"

        x, y, sw = no_mask_preprocessor(input_data)
        self.assertAllEqual(
            x["token_ids"], [1, 5, 10, 6, 8, 2, 0, 0, 0, 0, 0, 0]
        )
        self.assertAllEqual(
            x["padding_mask"], [1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0]
        )
        self.assertAllEqual(x["mask_positions"], [0, 0, 0, 0])
        self.assertAllEqual(y, [0, 0, 0, 0])
        self.assertAllEqual(sw, [0.0, 0.0, 0.0, 0.0])

    def test_serialization(self):
        config = keras.saving.serialize_keras_object(self.preprocessor)
        new_preprocessor = keras.saving.deserialize_keras_object(config)
        self.assertEqual(
            new_preprocessor.get_config(),
            self.preprocessor.get_config(),
        )
