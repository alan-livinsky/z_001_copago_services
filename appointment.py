from trytond.model import fields
from trytond.pool import PoolMeta


class Appointment(metaclass=PoolMeta):
    __name__ = 'gnuhealth.appointment'

    copago_paid = fields.Boolean('Copago pagado')
    copago_status = fields.Function(fields.Selection([
                ('pending', 'Pendiente'),
                ('paid', 'Pagado'),
                ], 'Estado copago'),
        'get_copago_status')

    def get_copago_status(self, name):
        return 'paid' if self.copago_paid else 'pending'
