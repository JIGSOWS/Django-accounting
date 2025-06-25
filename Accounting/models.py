from re import S
from django.db import models
from django.db.models import Sum
from django.db.models.signals import pre_save,post_delete,post_save,pre_delete
from django.dispatch import receiver
import bcrypt
from django.utils.crypto import get_random_string
from django.contrib.auth.models import BaseUserManager,AbstractBaseUser,PermissionsMixin
from .calculations import calculateTotalPrice, calculateUnit

# All Models Have Been Finnshed

class UserManager(BaseUserManager):
    def create_user(self, user_name, email, password=None, **extra_fields):
        if not email:
            raise ValueError('You Did Not Enter a Valid Email')

        email = self.normalize_email(email)
        user = self.model(user_name=user_name, email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, user_name, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(user_name, email, password, **extra_fields)
class User (AbstractBaseUser,PermissionsMixin):
    user_name = models.CharField(max_length=100,primary_key=True)
    email = models.CharField(max_length=250,unique=True)
    issatup = models.BooleanField(default=False)
    budget = models.FloatField(default=0)
    password_reset_code = models.CharField(max_length=20, blank=True, null=True)

    is_active = models.BooleanField(default=True,editable=False) 
    is_staff = models.BooleanField(default=False,editable=False) 
    is_superuser = models.BooleanField(default=False,editable=False) 
    date_joined = models.DateTimeField(auto_now_add=True)

    groups = models.ManyToManyField(
        'auth.Group',
        related_name='accounting_user_set',
        blank=True,
        help_text=('The groups this user belongs to. A user will get all permissions granted to each of their groups.'),
        verbose_name=('groups'),
        editable=False
    )
    user_permissions = models.ManyToManyField(
        'auth.Permission',
        related_name='accounting_user_permissions',
        blank=True,
        help_text=('Specific permissions for this user.'),
        verbose_name=('user permissions'),
        editable=False
    )

    objects = UserManager()

    USERNAME_FIELD = 'user_name'
    REQUIRED_FIELDS = ['email']

    def set_password(self,raw_password):
        hashed_password = bcrypt.hashpw(raw_password.encode('utf-8'), bcrypt.gensalt())
        self.password = hashed_password.decode('utf-8')
    def check_password(self,raw_password):
        return bcrypt.checkpw(raw_password.encode('utf-8'), self.password.encode('utf-8'))
    def __str__(self):
        return f'{self.user_name}'

@receiver(post_save, sender=User)
def create_money_fund(sender, instance, created, **kwargs):
    if created:
        MoneyFund.objects.create(user=instance)

@receiver(post_delete,sender = User)
def update_permanant_fund_on_delete(sender,instance,**kwargs):
    money_fund = MoneyFund.objects.get(user = instance.user_name)

    if money_fund:
        money_fund.permanant_fund -= instance.budget
        money_fund.save()

@receiver(pre_save, sender=User)
def update_permanant_fund_on_edit(sender, instance, **kwargs):
    try:
        if instance.pk:
            old_instance = User.objects.get(pk=instance.pk)
            old_budget = old_instance.budget
            new_budget = instance.budget
            money_fund = MoneyFund.objects.get(user=instance.user_name)
            
            if money_fund:
                money_fund.permanant_fund -= old_budget
                money_fund.permanant_fund += new_budget
                money_fund.save()
    except User.DoesNotExist:
        # This block will be executed during user creation, ignore it
        pass

class Type(models.Model):
    type = models.CharField(max_length=50)
    user = models.ForeignKey(User,on_delete=models.CASCADE)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'type'], 
                name='unique_user_type'
            )
        ]

    def __str__(self):
        return f'{self.type}'

class Supplies(models.Model):
    user = models.ForeignKey(User,on_delete=models.CASCADE)
    type = models.ForeignKey(Type,on_delete=models.CASCADE,default="")
    supply_name = models.CharField(max_length=50)
    unit = models.CharField(max_length=10,default='Peace')
    countity = models.FloatField(default=0)
    buy_price = models.FloatField(default=0)
    sell_price = models.FloatField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'supply_name'], 
                name='unique_user_supply'
            )
        ]

    def __str__(self):
        return f'{self.supply_name}'

class DispatchSupply(models.Model):
    user = models.ForeignKey(User,on_delete=models.CASCADE)
    supply = models.ForeignKey(Supplies,on_delete=models.CASCADE,default="")
    countity = models.FloatField(default=0)
    buy_price = models.FloatField(default=0)
    dispatch_date = models.DateField(null=True,blank=True)
    reason = models.CharField(max_length=400,null=True,blank=True)

    def __str__(self):
        return f'{self.supply} Countity: {self.countity}'

@receiver(post_save, sender=DispatchSupply)
def update_supply_and_fund(sender, instance, created, **kwargs):
    if created:
        supply = instance.supply
        countity = instance.countity
        buy_price = instance.buy_price

        if supply.countity >= countity:
            supply.countity -= countity
            supply.save()

            money_fund = MoneyFund.objects.get(user=instance.user)
            if money_fund.permanant_fund >= calculateTotalPrice(countity,supply.unit, buy_price):
                money_fund.permanant_fund -= calculateTotalPrice(countity,supply.unit, buy_price)
                money_fund.save()
            else:
                raise ValueError("Not enough funds")
        else:
            raise ValueError("Not enough supplies to dispatch")

@receiver(post_delete, sender=DispatchSupply)
def handle_dispatch_deletion(sender, instance, **kwargs):
    supply = instance.supply
    countity = instance.countity
    buy_price = instance.buy_price

    supply.countity += countity
    supply.save()

    money_fund = MoneyFund.objects.get(user=instance.user)
    money_fund.permanant_fund += calculateTotalPrice(countity,supply.unit, buy_price)
    money_fund.save()

@receiver(pre_save, sender=DispatchSupply)
def handle_dispatch_update(sender, instance, **kwargs):
    try:
        original = DispatchSupply.objects.get(pk=instance.pk,user=instance.user)
    except DispatchSupply.DoesNotExist:
        original = None

    if original:
        supply = instance.supply
        countity_difference = instance.countity - original.countity

        if supply.countity + original.countity >= instance.countity:
            supply.countity -= countity_difference
            supply.save()

            money_fund = MoneyFund.objects.get(user=instance.user)
            if money_fund.permanant_fund + calculateTotalPrice(original.countity ,supply.unit,  original.buy_price) >= calculateTotalPrice(instance.countity ,supply.unit,  instance.buy_price):
                money_fund.permanant_fund -= calculateTotalPrice(countity_difference ,supply.unit,  instance.buy_price)
                money_fund.save()

            else:
                raise ValueError("Not enough funds")
        else:
            raise ValueError("Not enough supplies to dispatch")

class CustomerName(models.Model):
    user = models.ForeignKey(User,on_delete=models.CASCADE)
    customer_name = models.CharField(max_length=50)
    total_debt = models.FloatField(null=True,blank=True,default=0)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'customer_name'], 
                name='unique_user_customer_name'
            )
        ]

    def __str__(self):
        return f'{self.customer_name}'

class Customer(models.Model):
    user = models.ForeignKey(User,on_delete=models.CASCADE)
    customer_name = models.ForeignKey(CustomerName,on_delete=models.CASCADE)
    date_of_buying = models.DateField(null=True,blank=True)
    supply = models.ForeignKey(Supplies,on_delete=models.CASCADE,default="")
    price = models.FloatField(default=0)
    countity = models.FloatField(default=0)
    total = models.FloatField(editable=False,default=0)
    debt = models.FloatField(default=0,null=True,blank=True)
    paid = models.FloatField(default=0,null=True,blank=True)
    notes = models.CharField(max_length=400,null=True,blank=True)

    def __str__(self):
        return f'{self.customer_name}'

#---------------------------------------------------------------
@receiver(pre_save, sender=Customer)
def capture_old_customer_instance(sender, instance, **kwargs):
    if instance.pk:
        try:
            instance._old_instance = Customer.objects.get(user=instance.user,pk=instance.pk)
        except Customer.DoesNotExist:
            instance._old_instance = None

@receiver(pre_delete, sender=Customer)
def capture_old_customer_value(sender, instance, **kwargs):
    instance._old_paid = instance.paid
    instance._old_debt = instance.debt
    instance._old_countity = instance.countity

@receiver(post_save, sender=Customer)
def handle_customer_save(sender, instance, created, **kwargs):
    money_fund = MoneyFund.objects.get(user=instance.user)
    customer_name, _ = CustomerName.objects.get_or_create(user=instance.user,customer_name=instance.customer_name.customer_name)
    supply = instance.supply

    # Handle creation and updates
    if created:
        if instance.debt == 0:
            if not money_fund:
                money_fund = MoneyFund.objects.create(user=instance.user,permanant_fund=0, sells_fund=0)
            money_fund.sells_fund += instance.total
        elif instance.debt > 0:
            if instance.paid > 0:
                money_fund.sells_fund += instance.paid
            customer_name.total_debt += instance.debt
        if supply:
            supply.countity -= instance.countity
            supply.save()
    else:
        old_instance = getattr(instance, '_old_instance', None)
        if old_instance:
            if old_instance.debt == 0 and money_fund:
                money_fund.sells_fund -= old_instance.total
            elif old_instance.debt > 0:
                if old_instance.paid > 0 and old_instance.debt > 0 and money_fund:
                    money_fund.sells_fund -= old_instance.paid
                customer_name.total_debt -= old_instance.debt

            if old_instance.countity != instance.countity:
                supply.countity += old_instance.countity - instance.countity
                supply.save()

            # Update new values
            if instance.debt == 0 and money_fund:
                money_fund.sells_fund += instance.total
            elif instance.debt > 0:
                if instance.paid > 0 and instance.debt > 0:
                    money_fund.sells_fund += instance.paid
                customer_name.total_debt += instance.debt

    money_fund.save()
    customer_name.save()

@receiver(post_delete, sender=Customer)
def handle_customer_deletion(sender, instance, **kwargs):
    customer_name = instance.customer_name
    old_paid = getattr(instance, '_old_paid', 0)
    old_debt = getattr(instance, '_old_debt', 0)
    old_countity = getattr(instance, '_old_countity', 0)
    money_fund = MoneyFund.objects.get(user=instance.user)

    if old_paid > 0 and money_fund:
        money_fund.sells_fund -= old_paid
        money_fund.save()

    if customer_name:
        customer_name.total_debt -= old_debt
        customer_name.save()

    supply = instance.supply
    if supply:
        supply.countity += old_countity
        supply.save()


#---------------------------------------------------------------
class Employee(models.Model):
    user = models.ForeignKey(User,on_delete=models.CASCADE)
    employee_name = models.CharField(max_length=50)
    date_of_employment = models.DateField(blank=True,null=True)
    salary = models.FloatField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'employee_name'], 
                name='unique_user_employee_name'
            )
        ]

    def __str__(self):
        return f'{self.employee_name}'

class MoneyFund(models.Model):
    user = models.OneToOneField(User,on_delete=models.CASCADE)
    permanant_fund = models.FloatField(default=0)
    sells_fund = models.FloatField(default=0)

    def __str__(self):
        return f'{self.permanant_fund} {self.sells_fund}'

class Sell(models.Model):
    user = models.ForeignKey(User,on_delete=models.CASCADE)
    supply = models.ForeignKey(Supplies,on_delete=models.CASCADE)
    countity = models.FloatField()
    price = models.FloatField()
    total = models.FloatField(default=0)
    date = models.DateField(null=True,blank=True)
    notes = models.CharField(max_length=400,null=True,blank=True)

    def __str__(self):
        return f'Date: {self.date} Supply: {self.supply} Total: {self.total}'

@receiver(post_save,sender=Sell)
def update_money_on_sell (sender,instance,**kwargs):
    money_fund = MoneyFund.objects.get(user=instance.user)
    
    if not money_fund:
        money_fund = MoneyFund.objects.create(user=instance.user,permanant_fund = 0,sells_fund = 0)
    
    money_fund.sells_fund += instance.total
    money_fund.save()

@receiver(post_delete,sender=Sell)
def update_money_delete_on_sell (sender,instance,**kwargs):
    money_fund = MoneyFund.objects.get(user=instance.user)
    
    if money_fund:
        money_fund.sells_fund -= instance.total
        money_fund.save()


@receiver(pre_save,sender=Sell)
def update_money_on_edit(sender,instance,**kwargs):
    if instance.pk:
        old_instance = Sell.objects.get(pk=instance.pk,user=instance.user)
        old_total = old_instance.total
        money_fund = MoneyFund.objects.get(user=instance.user)
        if money_fund:
            money_fund.sells_fund -= old_total
            money_fund.save()

#---------------------------------------------------------------
@receiver(post_save,sender=Sell)
def update_supply_on_sells(sender,instance,**kwargs):
     if instance.supply.pk:
         supply = Supplies.objects.get(supply_name = instance.supply,user=instance.user)
         if supply:   
             supply.countity -= instance.countity
             supply.save()

@receiver(post_delete,sender=Sell)
def update_supply_delete_on_sells(sender,instance,**kwargs):
    supply = Supplies.objects.get(supply_name = instance.supply,user=instance.user)

    if supply.pk:
        supply.countity += instance.countity
        supply.save()

@receiver(pre_save,sender=Sell)
def update_supply_edit_on_sells(sender,instance,**kwargs):
    if instance.pk:
        old_intance = Sell.objects.get(pk= instance.pk,user=instance.user)
        old_countity = old_intance.countity
        supply = Supplies.objects.get(supply_name= instance.supply,user=instance.user)
        if supply:
            supply.countity += old_countity
            supply.save()

class Reciept(models.Model):
    user = models.ForeignKey(User,on_delete=models.CASCADE)
    type = models.ForeignKey(Type,on_delete=models.CASCADE)
    supply = models.ForeignKey(Supplies,on_delete=models.CASCADE)
    countity = models.FloatField()
    buy_price = models.FloatField()
    sell_price = models.FloatField()
    total = models.FloatField(default=0)
    date = models.DateField(null=True,blank=True)
    notes = models.CharField(max_length=400,null=True,blank=True)

    def __str__(self):
        return f'Type: {self.type} Supply:{self.supply}'

#---------------------------------------------------------------

@receiver(post_save,sender=Reciept)
def update_money_on_reciepts(sender,instance,**kwargs):
    money_fund = MoneyFund.objects.get(user=instance.user)

    if not money_fund:
        money_fund = MoneyFund.objects.create(user=instance.user,permanant_fund = 0,sells_fund = 0)
    
    money_fund.permanant_fund -= instance.total
    money_fund.save()

@receiver(post_delete,sender=Reciept)
def update_money_delete_on_reciepts(sender,instance,**kwargs):
    money_fund = MoneyFund.objects.get(user=instance.user)

    if money_fund:
        money_fund.permanant_fund += instance.total
        money_fund.save()

@receiver(pre_save,sender=Reciept)
def update_money_ediut_on_reciepts(sender,instance,**kwargs):
    if instance.pk:
        old_instance = Reciept.objects.get(pk=instance.pk,user = instance.user)
        old_total = old_instance.total
        money_fund = MoneyFund.objects.get(user=instance.user)
        if money_fund:
            money_fund.permanant_fund += old_total
            money_fund.save()

#---------------------------------------------------------------

@receiver(post_save, sender=Reciept)
def update_supply_on_receipts(sender, instance, **kwargs):
    supply, created = Supplies.objects.get_or_create(
        user = instance.user,
        supply_name= instance.supply.supply_name,
        defaults={
            'countity': instance.countity,
            'buy_price': instance.buy_price,
            'sell_price': instance.sell_price,
            'type': instance.type,
        }
    )
    if not created:  # If the supply already exists, update the countity
        supply.countity += instance.countity
        supply.buy_price = instance.buy_price
        supply.sell_price = instance.sell_price
        supply.save()


@receiver(post_delete,sender=Reciept)
def update_supply_delete_on_receipts(sender,instance,**kwargs):
    supply = Supplies.objects.get(supply_name = instance.supply,user=instance.user)

    if supply.pk:
        supply.countity -= instance.countity 
        supply.save()

@receiver(pre_save,sender=Reciept)
def update_supply_edit_on_receipt(sender,instance,**kwargs):
    if instance.pk:
        old_intance = Reciept.objects.get(pk= instance.pk,user=instance.user)
        old_countity = old_intance.countity
        supply = Supplies.objects.get(supply_name= instance.supply,user=instance.user)
        if supply:
            supply.countity -= old_countity
            supply.save()

class MoneyIncome(models.Model):
    user = models.ForeignKey(User,on_delete=models.CASCADE)
    money_from = models.ForeignKey(CustomerName,on_delete=models.CASCADE,null=True,blank=True)
    total = models.FloatField(default=0)
    date = models.DateField(null=True,blank=True)
    notes = models.CharField(max_length=400,null=True,blank=True)

    def __str__(self):
        return f'Date: {self.date} Total: {self.total}'

#---------------------------------------------------------------

@receiver(post_delete, sender=MoneyIncome)
def reverse_debt_on_payment_deletion(sender, instance, **kwargs):
    customer_name = instance.money_from

    customers = Customer.objects.filter(customer_name=customer_name,user=instance.user).order_by('date_of_buying')
    
    remaining_payment = instance.total

    for customer in customers:
        if remaining_payment <= 0:
            break
        if customer.paid > 0:
            if remaining_payment >= customer.paid:
                remaining_payment -= customer.paid
                customer.debt += customer.paid  # Reverse the payment by adding it back to debt
                customer.paid = 0
                customer.notes = 'Reversed payment.'
            else:
                customer.debt += remaining_payment
                customer.paid -= remaining_payment  # Ensure correct decrement
                customer.notes = 'Partial payment reversal.'
                remaining_payment = 0
            customer.save()

@receiver(post_save, sender=MoneyIncome)
def update_debt_on_payment(sender, instance, created, **kwargs):
    customer_name = instance.money_from

    customers = Customer.objects.filter(customer_name=customer_name,user=instance.user).order_by('date_of_buying')
    
    remaining_payment = instance.total

    for customer in customers:
        if remaining_payment <= 0:
            break
        if customer.debt > 0:
            if remaining_payment >= customer.debt:
                remaining_payment -= customer.debt
                customer.paid += customer.debt 
                customer.debt = 0
                customer.notes = 'Debt has been paid.'
            else:
                customer.debt -= remaining_payment
                customer.paid += remaining_payment 
                customer.notes = 'Partial payment made.'
                remaining_payment = 0
            customer.save()


#---------------------------------------------------------------

class Payment(models.Model):
    user = models.ForeignKey(User,on_delete=models.CASCADE)
    money_for = models.CharField(max_length=250)
    total = models.FloatField(default=0)
    date = models.DateField(null=True,blank=True)
    notes = models.CharField(max_length=400,null=True,blank=True)

    def __str__(self):
        return f'Paid for: {self.money_for} Date: {self.date} Total: {self.total}'
    
#---------------------------------------------------------------
@receiver(post_save,sender=Payment)
def update_money_on_payment (sender,instance,**kwargs):
    money_fund = MoneyFund.objects.get(user=instance.user)
    
    if not money_fund:
        money_fund = MoneyFund.objects.create(user=instance.user,permanant_fund = 0,sells_fund = 0)
    
    money_fund.permanant_fund -= instance.total
    money_fund.save()

@receiver(post_delete,sender=Payment)
def update_money_delete_on_payment (sender,instance,**kwargs):
    money_fund = MoneyFund.objects.get(user=instance.user)
    
    if money_fund:
        money_fund.permanant_fund += instance.total
        money_fund.save()


@receiver(pre_save,sender=Payment)
def update_money_on_edit(sender,instance,**kwargs):
    if instance.pk:
        old_instance = Payment.objects.get(pk=instance.pk,user=instance.user)
        old_total = old_instance.total
        money_fund = MoneyFund.objects.get(user=instance.user)
        if money_fund:
            money_fund.permanant_fund += old_total
            money_fund.save()


#-------------------------------------------------------------------

class Inventory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    supply = models.ForeignKey(Supplies, on_delete=models.CASCADE)
    initial_countity = models.FloatField(blank=True)
    final_countity = models.FloatField(blank=True)
    initial_fund = models.FloatField(blank=True)
    final_fund = models.FloatField(blank=True)
    sales_countity = models.FloatField(default=0, blank=True)
    sales_value = models.FloatField(default=0,blank=True)

    purchase_countity = models.FloatField(default=0, blank=True)
    purchase_value = models.FloatField(default=0,blank=True)
    
    debt_countity = models.FloatField(default=0, blank=True)
    unpaid_customers = models.TextField(blank=True)
    discrepancy = models.FloatField(default=0, blank=True)
    dispatched_supply = models.FloatField(default=0, blank=True)
    dispatched_value = models.FloatField(default=0, blank=True)
    
    profits = models.FloatField(default=0,blank=True)

    start_date = models.DateField()
    end_date = models.DateField()
    inventory_date = models.DateField(auto_now=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f'Inventory for {self.supply} from {self.start_date} to {self.end_date}'

    def calculate_inventory(self):
        # Retrieve initial values
        self.initial_countity = self.supply.countity
        money_fund = MoneyFund.objects.get(user=self.user)
        self.initial_fund = money_fund.sells_fund if money_fund else 0

        # Retrieve data from the models
        sales = Sell.objects.filter(date__range=[self.start_date, self.end_date], supply=self.supply).aggregate(Sum('countity'))['countity__sum'] or 0
        
        sells_value = Sell.objects.filter(date__range=[self.start_date,self.end_date],supply=self.supply).aggregate(Sum('total'))['total__sum'] or 0
        purchases_value = Reciept.objects.filter(date__range=[self.start_date,self.end_date],supply=self.supply).aggregate(Sum('buy_price'))['buy_price__sum'] or 0

        debt_paid = Customer.objects.filter(date_of_buying__range=[self.start_date, self.end_date],supply=self.supply,debt=0 ).aggregate(Sum('countity'))['countity__sum'] or 0
        purchases = Reciept.objects.filter(date__range=[self.start_date, self.end_date], supply=self.supply).aggregate(Sum('countity'))['countity__sum'] or 0
        unpaid_customers_query = Customer.objects.filter(date_of_buying__range=[self.start_date, self.end_date], debt__gt=0, supply=self.supply)
        unpaid_customers_list = unpaid_customers_query.values_list('customer_name__customer_name', flat=True)
        unpaid_customers_str = ', '.join(unpaid_customers_list)
        unpaid_debts = unpaid_customers_query.aggregate(Sum('debt'))['debt__sum'] or 0
        unpaid_countity = unpaid_customers_query.aggregate(Sum('countity'))['countity__sum'] or 0
        income_total = MoneyIncome.objects.filter(date__range=[self.start_date, self.end_date]).aggregate(Sum('total'))['total__sum'] or 0
        expense_total = Payment.objects.filter(date__range=[self.start_date, self.end_date]).aggregate(Sum('total'))['total__sum'] or 0

        # Retrieve dispatched data
        dispatches = DispatchSupply.objects.filter(dispatch_date__range=[self.start_date, self.end_date], supply=self.supply)
        dispatched_countity = dispatches.aggregate(Sum('countity'))['countity__sum'] or 0
        dispatched_value = sum(dispatch.buy_price * dispatch.countity * calculateUnit(dispatch.supply.unit) for dispatch in dispatches)
       

        # Calculate updated quantities and funds
        self.sales_countity = sales + debt_paid
        self.sales_value = sells_value
        self.purchase_countity = purchases
        self.purchase_value = purchases_value
        self.debt_countity = unpaid_countity
        self.dispatched_supply = dispatched_countity
        self.dispatched_value = dispatched_value
        self.final_countity = self.initial_countity + (purchases - sales - unpaid_countity - dispatched_countity)
        self.unpaid_customers = unpaid_customers_str

        expected_countity = self.initial_countity + purchases - sales - dispatched_countity
        self.discrepancy = self.final_countity - expected_countity

        # Calculating Profits
        self.profits = (sells_value - purchases_value) - dispatched_value
        

        # Check if final countity is accurate
        if self.final_countity != self.initial_countity + purchases - sales - unpaid_countity - dispatched_countity:
            self.notes = 'Losses detected due to inventory miscalculation.'
        else:
            self.notes = 'No losses detected.'

        # Calculate final fund and handle discrepancies
        if money_fund:
            self.final_fund = self.initial_fund + income_total - expense_total - dispatched_value
            # if self.discrepancy != 0:
            #     money_fund.sells_fund += self.discrepancy
            #     money_fund.save()
            if self.final_fund < 0:
                self.notes += ' Warning: Final fund is negative.'

    def save(self, *args, **kwargs):
        self.calculate_inventory()
        super(Inventory, self).save(*args, **kwargs)

@receiver(post_save, sender=Inventory)
def inventory_post_save(sender, instance, created, **kwargs):
    if created:
        instance.calculate_inventory()