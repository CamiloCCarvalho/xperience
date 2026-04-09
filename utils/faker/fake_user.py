# from inspect import signature
from random import randint

from faker import Faker


def rand_ratio():
    return randint(840, 900), randint(473, 573)

fake = Faker('pt_BR')

def make_user_data():
    return {
        'user_name': fake.sentence(nb_words=2),
        'id': fake.random_int(min=1, max=999),
        'user_avatar': {
            'url': 'https://loremflickr.com/%s/%s/food,cook' % rand_ratio(),
        }
    }

def make_user_avatar():
    return {
        'user_avatar_url': 'https://loremflickr.com/%s/%s/food,cook' % rand_ratio(),
    }

if __name__ == '__main__':
    from pprint import pprint
    pprint(make_user_data())