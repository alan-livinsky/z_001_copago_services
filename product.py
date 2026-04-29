from trytond.model import fields
from trytond.pool import PoolMeta


class Product(metaclass=PoolMeta):
    __name__ = 'product.product'

    copago_individual_ticket = fields.Boolean(
        'Generar ticket individual')
