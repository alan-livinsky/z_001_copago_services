import datetime
from collections import OrderedDict

from trytond.exceptions import UserError
from trytond.model import ModelView, fields
from trytond.pool import Pool
from trytond.transaction import Transaction
from trytond.wizard import Button, StateReport, StateView, Wizard


COPAGO_EXEMPTION_FIELDS = (
    'copago_exempt_pregnant',
    'copago_exempt_disabled',
    'copago_exempt_oncology',
    'copago_exempt_gynecology',
    'copago_exempt_under_one_year',
    'copago_exempt_recent_surgery',
)


class AppointmentCopagoV4Start(ModelView):
    'Appointment Copago V4 Start'
    __name__ = 'gnuhealth.appointment.copago.v4.start'

    patient = fields.Many2One('gnuhealth.patient', 'Paciente', readonly=True)
    copago_exemption_status = fields.Char(
        'Estado de excepcion de pago', readonly=True)
    products = fields.Many2Many(
        'product.product', None, None, 'Servicios',
        domain=[
            ('type', '=', 'service'),
            ('is_copago_service', '=', True),
        ],
        depends=['patient'])
    observaciones = fields.Text('Observaciones')

    @staticmethod
    def _get_appointment():
        pool = Pool()
        Appointment = pool.get('gnuhealth.appointment')

        active_ids = Transaction().context.get('active_ids') or []
        if len(active_ids) != 1:
            raise UserError('Seleccione una sola cita.')
        appointment = Appointment(active_ids[0])
        if getattr(appointment, 'copago_paid', False):
            raise UserError('El correspondiente copago ya figura como pagado.')
        return appointment

    @classmethod
    def default_patient(cls):
        appointment = cls._get_appointment()
        if not appointment.patient:
            raise UserError('La cita seleccionada no tiene un paciente asignado.')
        return appointment.patient.id

    @classmethod
    def default_copago_exemption_status(cls):
        appointment = cls._get_appointment()
        if cls._is_patient_exempt(appointment.patient):
            return 'Paciente exceptuado de pago.'
        return 'Paciente no exceptuado de pago.'

    @staticmethod
    def _is_patient_exempt(patient):
        if not patient:
            return False
        return any(
            bool(getattr(patient, field_name, False))
            for field_name in COPAGO_EXEMPTION_FIELDS
        )


class GenerateAppointmentCopagoV4(Wizard):
    'Generate Appointment Copago V4'
    __name__ = 'wizard.gnuhealth.appointment.copago.v4'

    start = StateView(
        'gnuhealth.appointment.copago.v4.start',
        'z_001_copago_services.appointment_copago_v4_start_view_form', [
            Button('Cancel', 'end', 'tryton-cancel'),
            Button('Generar', 'print_', 'tryton-ok', default=True),
        ])
    print_ = StateReport('z_001_copago_services.invoice')

    def do_print_(self, action):
        invoices = self._generate_copago_v4()
        data = {
            'id': invoices[0].id,
            'ids': [invoice.id for invoice in invoices],
            'model': 'account.invoice',
        }
        return action, data

    def transition_print_(self):
        return 'end'

    def _generate_copago_v4(self):
        pool = Pool()
        Invoice = pool.get('account.invoice')
        Appointment = pool.get('gnuhealth.appointment')

        products = list(self.start.products or [])
        if not products:
            raise UserError('Seleccione al menos un producto de copago.')
        self._validate_copago_products(products)

        service = self._create_health_service(products)
        lines = list(service.service_line)

        invoice_groups = self._build_invoice_groups(lines)
        invoices = []
        for _, group_lines in invoice_groups.items():
            invoice = self._create_invoice(group_lines)
            invoices.append(invoice)
            self._mark_lines_invoiced(group_lines, invoice)

        self._update_parent_services(lines)

        appointment = Appointment(AppointmentCopagoV4Start._get_appointment().id)
        Appointment.write([appointment], {
            'copago_paid': True,
        })

        Invoice.read([invoice.id for invoice in invoices], ['id'])
        return invoices

    @staticmethod
    def _validate_copago_products(products):
        invalid_products = []
        for product in products:
            product_name = (
                getattr(product, 'name', None)
                or getattr(product, 'rec_name', None)
                or str(product.id)
            )
            if not getattr(product, 'is_copago_service', False):
                invalid_products.append(product_name)

        if invalid_products:
            raise UserError(
                'Solo se permiten productos configurados para copago: %s'
                % ', '.join(invalid_products)
            )

    def _create_health_service(self, products):
        pool = Pool()
        HealthService = pool.get('gnuhealth.health_service')

        appointment = AppointmentCopagoV4Start._get_appointment()
        patient = appointment.patient
        today = datetime.date.today()
        company_id = Transaction().context.get('company')
        if not company_id:
            raise UserError('No existe una compañía por defecto en el contexto actual.')

        service_line = []
        for product in products:
            service_line.append(('create', [{
                'product': product.id,
                'desc': getattr(product, 'name', None) or product.rec_name,
                'qty': 1,
                'from_date': today,
                'to_date': today,
                'appointment': appointment.id,
                'remarks': self.start.observaciones,
                'to_invoice': True,
                'requires_individual_invoice': bool(
                    getattr(product, 'copago_individual_ticket', False)),
            }]))

        service, = HealthService.create([{
            'patient': patient.id,
            'desc': 'Copago',
            'institution': self._get_institution(),
            'company': company_id,
            'service_date': today,
            'invoice_to': patient.name.id,
            'service_line': service_line,
        }])
        return service

    def _build_invoice_groups(self, lines):
        groups = OrderedDict()
        for line in lines:
            party = line.name.invoice_to or line.name.patient.name
            company = line.name.company
            if line.requires_individual_invoice:
                key = ('individual', line.id)
            else:
                key = ('grouped', party.id, company.id if company else None)
            groups.setdefault(key, []).append(line)
        return groups

    def _create_invoice(self, lines):
        pool = Pool()
        Invoice = pool.get('account.invoice')

        invoice_data = self._get_invoice_header(lines)
        invoice_data['lines'] = self._get_invoice_lines(lines)
        invoice, = Invoice.create([invoice_data])
        Invoice.update_taxes([invoice])
        return invoice

    def _get_invoice_header(self, lines):
        pool = Pool()
        Party = pool.get('party.party')
        Journal = pool.get('account.journal')
        AcctConfig = pool.get('account.configuration')

        first_line = lines[0]
        service = first_line.name
        party = service.invoice_to or service.patient.name
        acct_config = AcctConfig(1)

        invoice_data = {
            'description': self._get_invoice_description(lines),
            'party': party.id,
            'type': 'out',
            'invoice_date': datetime.date.today(),
            'company': service.company.id if service.company else None,
            'reference': self._get_invoice_reference(lines),
            'comment': self.start.observaciones,
        }

        if party.account_receivable:
            invoice_data['account'] = party.account_receivable.id
        elif acct_config.default_account_receivable:
            invoice_data['account'] = acct_config.default_account_receivable.id
        else:
            raise UserError('No existe una cuenta por cobrar por defecto en la configuración de la empresa.')

        journals = Journal.search([
            ('type', '=', 'revenue'),
        ], limit=1)
        if not journals:
            raise UserError('No existe un diario de ingresos configurado.')
        invoice_data['journal'] = journals[0].id

        party_address = Party.address_get(party, type='invoice')
        if not party_address:
            raise UserError('La factura no tiene una dirección de facturación.')
        invoice_data['invoice_address'] = party_address.id

        if party.customer_payment_term:
            invoice_data['payment_term'] = party.customer_payment_term.id
        elif acct_config.default_customer_payment_term:
            invoice_data['payment_term'] = (
                acct_config.default_customer_payment_term.id)
        else:
            raise UserError('No existe un plazo de pago para clientes por defecto en la configuración de la empresa.')

        return invoice_data

    def _get_invoice_lines(self, lines):
        invoice_lines = []
        sequence = 0
        zero_amount = self._is_zero_copay_case()
        for line in lines:
            if not line.to_invoice:
                continue
            sequence += 1
            account = line.product.template.account_revenue_used
            if not account:
                raise UserError(
                    'El producto de servicio seleccionado no tiene una cuenta de ingresos.')

            unit_price = self._compute_unit_price(line)
            if zero_amount:
                unit_price = 0

            taxes = [tax.id for tax in line.product.customer_taxes_used]
            invoice_lines.append(('create', [{
                'origin': str(line),
                'product': line.product.id,
                'description': line.desc,
                'quantity': line.qty,
                'account': account.id,
                'unit': line.product.default_uom.id,
                'unit_price': unit_price,
                'sequence': sequence,
                'taxes': [('add', taxes)],
            }]))

        if not invoice_lines:
            raise UserError('Las líneas seleccionadas no contienen artículos facturables.')
        return invoice_lines

    def _compute_unit_price(self, line):
        currency_id = Transaction().context.get('currency')
        service = line.name
        party = service.invoice_to or service.patient.name
        sale_price_list = getattr(party, 'sale_price_list', None)
        if not sale_price_list:
            return line.product.list_price

        with Transaction().set_context({
            'price_list': sale_price_list.id,
            'sale_date': datetime.date.today(),
            'currency': currency_id,
            'customer': party.id,
        }):
            return sale_price_list.compute(
                party,
                line.product,
                line.product.list_price,
                line.qty,
                line.product.default_uom)

    def _is_zero_copay_case(self):
        return AppointmentCopagoV4Start._is_patient_exempt(self.start.patient)

    @staticmethod
    def _mark_lines_invoiced(lines, invoice):
        pool = Pool()
        HealthServiceLine = pool.get('gnuhealth.health_service.line')
        HealthServiceLine.write(lines, {
            'copago_invoice': invoice.id,
        })

    @staticmethod
    def _update_parent_services(lines):
        pool = Pool()
        HealthService = pool.get('gnuhealth.health_service')

        service_map = {}
        for line in lines:
            service_map[line.name.id] = line.name

        services = []
        for service in service_map.values():
            pending_lines = [
                current_line for current_line in service.service_line
                if current_line.to_invoice and not current_line.copago_invoice
            ]
            if not pending_lines:
                services.append(service)

        if services:
            HealthService.write(services, {
                'state': 'invoiced',
            })

    @staticmethod
    def _get_invoice_description(lines):
        if len(lines) == 1:
            return 'Copago v4 - %s' % lines[0].desc
        return 'Copago v4 consolidado'

    @staticmethod
    def _get_invoice_reference(lines):
        references = []
        for line in lines:
            if line.name.name not in references:
                references.append(line.name.name)
        return ', '.join(references[:5])

    @staticmethod
    def _get_institution():
        from trytond.modules.health.core import get_institution
        return get_institution()
