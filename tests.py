import unittest
import time

from scoring import score

class ScoringTests(unittest.TestCase):
    def test_yellowAnnoyance(self):
        f = ['BBBGYGGBrrBGBG',
             'BBGYBYYBrrGGGB',
             'BGrrBYBBrrrrBG',
             'BGrrGYrYrrrrBG',
             'GGGYYBYBYGBBGG',
             'YBGYBYBYrYYBGB',
             'GBGrYGYYYGrrGG',
             'BGGYGYYYGYrrGG',
             'YBBYYrrYYrYBGG',
             'BBBGBGBBYGBGYB']
        scores = score(f, True)
        s = time.monotonic()
        scores = score(f, True)
        print(time.monotonic() - s)
        self.assertEqual(scores, {'B': 8, 'G': 16, 'Y': 30, 'total': 54})

    def test_yellowPain(self):
        f = ['BBBGYGGBrrBGBG',
             'BBGYBYYBrrGGGB',
             'BGrrBYBBrrrrBG',
             'BGrrGYYYrrrrBG',
             'GGGYYBYBYGBBGG',
             'YBGYBYBYYYYBGB',
             'GBGrYGYYYGrrGG',
             'BGGYGYYYGYrrGG',
             'YBBYYrYYYrYBGG',
             'BBBGBGBBYGBGYB']
        scores = score(f, True)
        s = time.monotonic()
        scores = score(f, True)
        print(time.monotonic() - s)
        self.assertEqual(scores, {'B': 8, 'G': 16, 'Y': 33, 'total': 57})

    def test_yellowAgony(self):
        f = ['BBBGYGGBrrBGBG',
             'BBGYBYYBrrGGGB',
             'BGrrBYBBrrrrBG',
             'BGrrGYYYrrrrBG',
             'GGGYYBYBYGBBGG',
             'YBGYBYBYYYYBGB',
             'GBGYYGYYYGrrGG',
             'BGGYGYYYGYrrGG',
             'YBBYYYYYYYYBGG',
             'BBBGBGBBYGBGYB']
        scores = score(f, True)
        self.assertEqual(scores, "I can't even get the result")


if __name__ == '__main__':
    unittest.main()
