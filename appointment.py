from trytond.model import fields
from trytond.pool import PoolMeta


class Appointment(metaclass=PoolMeta):
    __name__ = 'gnuhealth.appointment'

    copago_paid = fields.Boolean('Copago pagado')
