from trytond.model import fields
from trytond.pool import PoolMeta


class HealthServiceLine(metaclass=PoolMeta):
    __name__ = 'gnuhealth.health_service.line'

    requires_individual_invoice = fields.Boolean(
        'Generar ticket individual')
    copago_invoice = fields.Many2One(
        'account.invoice', 'Factura generada', readonly=True)
