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
from keras_nlp.models.deberta_v3.deberta_v3_preprocessor import (
    DebertaV3Preprocessor,
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

        self.preprocessor = DebertaV3Preprocessor(
            tokenizer=DebertaV3Tokenizer(proto=self.proto),
            sequence_length=12,
        )

    def test_tokenize_strings(self):
        input_data = "the quick brown fox"
        output = self.preprocessor(input_data)
        self.assertAllEqual(
            output["token_ids"], [1, 5, 10, 6, 8, 2, 0, 0, 0, 0, 0, 0]
        )
        self.assertAllEqual(
            output["padding_mask"], [1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0]
        )

    def test_tokenize_list_of_strings(self):
        # We should handle a list of strings as as batch.
        input_data = ["the quick brown fox"] * 4
        output = self.preprocessor(input_data)
        self.assertAllEqual(
            output["token_ids"], [[1, 5, 10, 6, 8, 2, 0, 0, 0, 0, 0, 0]] * 4
        )
        self.assertAllEqual(
            output["padding_mask"], [[1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0]] * 4
        )

    def test_tokenize_labeled_batch(self):
        x = tf.constant(["the quick brown fox"] * 4)
        y = tf.constant([1] * 4)
        sw = tf.constant([1.0] * 4)
        x_out, y_out, sw_out = self.preprocessor(x, y, sw)
        self.assertAllEqual(
            x_out["token_ids"], [[1, 5, 10, 6, 8, 2, 0, 0, 0, 0, 0, 0]] * 4
        )
        self.assertAllEqual(
            x_out["padding_mask"], [[1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0]] * 4
        )
        self.assertAllEqual(y_out, y)
        self.assertAllEqual(sw_out, sw)

    def test_tokenize_labeled_dataset(self):
        x = tf.constant(["the quick brown fox"] * 4)
        y = tf.constant([1] * 4)
        sw = tf.constant([1.0] * 4)
        ds = tf.data.Dataset.from_tensor_slices((x, y, sw))
        ds = ds.map(self.preprocessor)
        x_out, y_out, sw_out = ds.batch(4).take(1).get_single_element()
        self.assertAllEqual(
            x_out["token_ids"], [[1, 5, 10, 6, 8, 2, 0, 0, 0, 0, 0, 0]] * 4
        )
        self.assertAllEqual(
            x_out["padding_mask"], [[1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0]] * 4
        )
        self.assertAllEqual(y_out, y)
        self.assertAllEqual(sw_out, sw)

    def test_tokenize_multiple_sentences(self):
        sentence_one = tf.constant("the quick brown fox")
        sentence_two = tf.constant("the earth")
        output = self.preprocessor((sentence_one, sentence_two))
        self.assertAllEqual(
            output["token_ids"], [1, 5, 10, 6, 8, 2, 5, 7, 2, 0, 0, 0]
        )
        self.assertAllEqual(
            output["padding_mask"], [1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0]
        )

    def test_tokenize_multiple_batched_sentences(self):
        sentence_one = tf.constant(["the quick brown fox"] * 4)
        sentence_two = tf.constant(["the earth"] * 4)
        # The first tuple or list is always interpreted as an enumeration of
        # separate sequences to concatenate.
        output = self.preprocessor((sentence_one, sentence_two))
        self.assertAllEqual(
            output["token_ids"], [[1, 5, 10, 6, 8, 2, 5, 7, 2, 0, 0, 0]] * 4
        )
        self.assertAllEqual(
            output["padding_mask"], [[1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0]] * 4
        )

    def test_errors_for_2d_list_input(self):
        ambiguous_input = [["one", "two"], ["three", "four"]]
        with self.assertRaises(ValueError):
            self.preprocessor(ambiguous_input)

    def test_serialization(self):
        config = keras.saving.serialize_keras_object(self.preprocessor)
        new_preprocessor = keras.saving.deserialize_keras_object(config)
        self.assertEqual(
            new_preprocessor.get_config(),
            self.preprocessor.get_config(),
        )
