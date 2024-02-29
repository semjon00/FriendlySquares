import unittest
import time

from scoring import score

class ScoringTests(unittest.TestCase):
    def setUp(self):
        score(['BB', 'BB'], False)
        score(['BB', 'BB'], True)

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
        s = time.monotonic()
        scores = score(f, False)
        print('annoyance', scores, time.monotonic() - s)

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
        s = time.monotonic()
        scores = score(f, False)
        print('pain', scores, time.monotonic() - s)
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
        s = time.monotonic()
        scores = score(f, False)
        print('agony', scores, time.monotonic() - s)


if __name__ == '__main__':
    unittest.main()
