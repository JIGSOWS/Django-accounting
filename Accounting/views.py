import pandas as pd
import logging
from django.http import JsonResponse
from django.db import  transaction
from django.http import HttpResponse
from .models import *
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate,Paragraph,PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from rest_framework_simplejwt.tokens import RefreshToken
from .serializers import *
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework.decorators import api_view,permission_classes
from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status
from .calculations import calculateTotalPrice
from PIL import Image
import base64
from io import BytesIO
from .utils import analyze_image
from rest_framework.views import APIView

logger = logging.getLogger(__name__)

# Login
class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = TokenObtainSerializer

@api_view(['POST'])
def logout(request):
    try:
        refresh_token = request.data["refresh"]
        token = RefreshToken(refresh_token)
        token.blacklist()
        return Response(status=status.HTTP_205_RESET_CONTENT)
    except Exception as e:
        return Response(status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
@permission_classes([AllowAny])
def register(request):
    username = request.data.get('username')
    email = request.data.get('email')
    password = request.data.get('password')
    resetcode = request.data.get('resetCode')

    if User.objects.filter(user_name=username).exists():
        return Response({'error': 'Username already exists'}, status=status.HTTP_400_BAD_REQUEST)

    if User.objects.filter(email=email).exists():
        return Response({'error': 'Email already exists'}, status=status.HTTP_400_BAD_REQUEST)

    user = User(user_name=username,email=email,budget = 0,password_reset_code=resetcode)
    user.set_password(password)
    user.save()

    user_serializer = UserSerializer(user)
    return Response(user_serializer.data, status=status.HTTP_201_CREATED)

@api_view(['POST'])
@permission_classes([AllowAny])
def reset_password(request):
    username = request.data.get('username')
    email = request.data.get('email')
    reset_code = request.data.get('reset_code')
    new_password = request.data.get('new_password')

    try:
        user = User.objects.get(user_name=username,email = email,password_reset_code = reset_code)
        user.set_password(new_password)
        user.save()
       # Generate new tokens
        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)
        refresh_token = str(refresh)

        return Response({
            'message': 'Password reset successful',
            'access_token': access_token,
            'refresh_token': refresh_token
        }, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({'error': 'Invalid username, email, or reset code'}, status=status.HTTP_400_BAD_REQUEST)

# ------------------------------------------------------------------------------------


# Setting Up Account EndPoint

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def setupAccount(request,username):
    issatup = request.data.get('issatup')
    budget = float(request.data.get('budget'))
    types = request.data.get('types',[])
    customernames = request.data.get('customers',[])
    employees = request.data.get('employees',[])

    try:
        user = User.objects.get(user_name = username)
        user.budget = budget
        user.issatup = issatup
        user.save()

       
        if types:
            for type_name in types:
                Type.objects.create(user=user, type=type_name)
               

        # Save customer names
        if customernames:
            for customer in customernames:
                CustomerName.objects.create(user=user, customer_name=customer)

        # Save employees
        if employees:
            for employee in employees:
                Employee.objects.create(user=user, employee_name=employee)
        
        if budget:
            MoneyFund.objects.create(user=user,sells_fund=0,permanant_fund= budget)
        
        return Response({'message': 'Setup successful!'}, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        logger.error("User not found for setup")
        return Response({'error': 'User not found'}, status=status.HTTP_400_BAD_REQUEST)
# ------------------------------------------------------------------------------------

# Managing Types End Points

@api_view(['POST','GET'])
@permission_classes([IsAuthenticated])
def manage_types(request,username):
    try:
        user = User.objects.get(user_name = username)

        if request.method == 'POST':
            types = request.data.get('types')
            user_data = request.data.get('user')

            if types and user_data:
                user_instance = User.objects.get(user_name = user_data)
                Type.objects.create(type=types,user = user_instance)

            return Response({'message': 'Type Added Successfully!'}, status=status.HTTP_200_OK)

        if request.method == 'GET':
            types = Type.objects.filter(user=user)
            serializer = TypeSerializer(types, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
    except User.DoesNotExist:
        return Response({'error': 'User not found'})
    except Exception as e:
        logger.error(f"Type error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def edit_types(request, username):
    try:
        user_instance = User.objects.get(user_name=username)

        if request.method == 'PUT':
            old_type = request.data.get('old_type')
            new_type = request.data.get('new_type')

            if old_type and new_type:
                try:
                    type_instance = Type.objects.get(type=old_type, user=user_instance)
                    type_instance.delete()
                    Type.objects.create(type = new_type,user = user_instance)
                    return Response({'message': 'Type updated successfully!'}, status=status.HTTP_200_OK)
                except Type.DoesNotExist:
                    return Response({'error': 'Type not found'}, status=status.HTTP_404_NOT_FOUND)

        elif request.method == 'DELETE':
            type_to_delete = request.data.get('type')

            if type_to_delete:
                try:
                    type_instance = Type.objects.get(type=type_to_delete, user=user_instance)
                    type_instance.delete()
                    return Response({'message': 'Type deleted successfully!'}, status=status.HTTP_200_OK)
                except Type.DoesNotExist:
                    return Response({'error': 'Type not found'}, status=status.HTTP_404_NOT_FOUND)

    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"EditTypes error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_type(request, username, type):
    try:
        user_instance = User.objects.get(user_name=username)
        types = Type.objects.filter(Q(type__icontains=type), user=user_instance)
        serializer = TypeSerializer(types, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Getting Types error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ------------------------------------------------------------------------------------

# Managing Supplies EndPoints

@api_view(['POST','GET'])
@permission_classes([IsAuthenticated])
def manage_supplies(request,username):
    try:
        user = User.objects.get(user_name = username)

        if request.method == 'POST':
            user_data = request.data.get('user')
            types = request.data.get('types')
            supplies = request.data.get('supplies')
            unit = request.data.get('unit')
            countity = float(request.data.get('countity'))
            buy_price = float(request.data.get('buy_price'))
            sell_price = float(request.data.get('sell_price'))
           
            if user_data:
                user_instance = User.objects.get(user_name = user_data)
                type_instance = Type.objects.get(user=user_instance,type = types)
                Supplies.objects.create(user= user_instance,type = type_instance,
                                        supply_name=supplies,unit = unit,
                                        countity=countity,buy_price=buy_price,
                                        sell_price=sell_price)

            return Response({'message': 'Supply Added Successfully!'}, status=status.HTTP_200_OK)

        if request.method == 'GET':
            supplies = Supplies.objects.filter(user=user)
            serializer = SuppliesSerializer(supplies, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
    except User.DoesNotExist:
        return Response({'error': 'User not found'})
    except Exception as e:
        logger.error(f"Supply error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def edit_supplies(request, username):
    try:
        user_instance = User.objects.get(user_name=username)

        if request.method == 'PUT':
            type = request.data.get('type')
            supply_name = request.data.get('supply_name')
            unit = request.data.get('unit')
            countity = float(request.data.get('countity'))
            buy_price = float(request.data.get('buy_price'))
            sell_price = float(request.data.get('sell_price'))
            newSupply = request.data.get('newSupply')

            if supply_name:
                try:
                    supply_instance = Supplies.objects.get(supply_name=supply_name, user=user_instance)
                    supply_instance.delete()
                    supply_instance.type = Type.objects.get(type = type,user=user_instance)
                    supply_instance.supply_name = newSupply
                    supply_instance.unit = unit
                    supply_instance.countity = countity
                    supply_instance.buy_price = buy_price
                    supply_instance.sell_price = sell_price
                    supply_instance.save()

                    
                    return Response({'message': 'Supply updated successfully!'}, status=status.HTTP_200_OK)
                except Supplies.DoesNotExist:
                    return Response({'error': 'Supply not found'}, status=status.HTTP_404_NOT_FOUND)

        elif request.method == 'DELETE':
            supply_to_delete = request.data.get('supply')

            if supply_to_delete:
                try:
                    supply_instance = Supplies.objects.get(supply_name=supply_to_delete, user=user_instance)
                    supply_instance.delete()
                    return Response({'message': 'Supply deleted successfully!'}, status=status.HTTP_200_OK)
                except Type.DoesNotExist:
                    return Response({'error': 'Supply not found'}, status=status.HTTP_404_NOT_FOUND)

    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"EditSupplies error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_types_and_supplies(request, username, query):
    try:
        user_instance = User.objects.get(user_name=username)
        
        # Search for supplies by supply_name and related type
        supplies = Supplies.objects.filter(
            Q(supply_name__icontains=query) | Q(type__type__icontains=query), user=user_instance
        )
        supplies_serializer = SuppliesSerializer(supplies, many=True)
        
        # Search for types
        types = Type.objects.filter(Q(type__icontains=query), user=user_instance)
        types_serializer = TypeSerializer(types, many=True)
        
        return Response({
            'supplies': supplies_serializer.data,
            'types': types_serializer.data
        }, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Search Supplies And Types error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_supplies(request, username,type, query):
    try:
        user_instance = User.objects.get(user_name=username)
        type_instance = Type.objects.get(user=user_instance,type=type)

        # Search for supplies by supply_name and related type
        supplies = Supplies.objects.filter(
            Q(supply_name__icontains=query), user=user_instance,type=type_instance
        )
        supplies_serializer = SuppliesSerializer(supplies, many=True)
                
        return Response({
            'supplies': supplies_serializer.data,
        }, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Search Supplies error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_only_supplies(request, username, query):
    try:
        user_instance = User.objects.get(user_name=username)

        # Search for supplies by supply_name and related type
        supplies = Supplies.objects.filter(
            Q(supply_name__icontains=query),user=user_instance
        )
        supplies_serializer = SuppliesSerializer(supplies, many=True)
                
        return Response({
            'supplies': supplies_serializer.data,
        }, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Search Only Supplies error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ------------------------------------------------------------------------------------

# Managing Reciepts EndPoints

@api_view(['POST','GET'])
@permission_classes([IsAuthenticated])
def reciepts(request,username):
    try:
        user = User.objects.get(user_name = username)

        if request.method == 'POST':
            user_data = request.data.get('user')
            types = request.data.get('types')
            supplies = request.data.get('supplies')
            countity = float(request.data.get('countity'))
            buy_price = float(request.data.get('buy_price'))
            sell_price = float(request.data.get('sell_price'))
            date = request.data.get('date')
            notes = request.data.get('notes')
            
            if user_data:
                user_instance = User.objects.get(user_name = user_data)
                type_instance = Type.objects.get(user=user_instance,type = types)
               

                if type_instance:
                    try:
                        supplies_instance = Supplies.objects.get(supply_name = supplies,user = user_instance)
                    except:
                        Supplies.objects.create(user=user_instance,type=type_instance,supply_name=supplies)
                        supplies_instance = Supplies.objects.get(supply_name = supplies,user = user_instance)

                    Reciept.objects.create(user=user_instance,type=type_instance,
                                            supply=supplies_instance,countity=countity,buy_price=buy_price,
                                            sell_price=sell_price,
                                            total = calculateTotalPrice(countity,supplies_instance.unit,buy_price),
                                            date = date,
                                            notes=notes)
                        
                    return Response({'message': 'Supplies Bought successfully!'}, status=status.HTTP_200_OK)
                else:
                    return Response({'message': 'Type Does Not Exists Please Insert And Existing Type'},status=status.HTTP_404_NOT_FOUND)
                
        
        if request.method == 'GET':
            reciepts = Reciept.objects.filter(user=user)
            serializer = RecieptSerializer(reciepts, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
    except User.DoesNotExist:
        logger.error(f"User {username} not found.")
        return Response({'error': 'User not found'})
    except Exception as e:
        logger.error(f"Reciept error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def edit_reciepts(request, username):
    try:
        user_instance = User.objects.get(user_name=username)

        if request.method == 'PUT':
            id = float(request.data.get('id'))
            types = request.data.get('type')
            supplies = request.data.get('supply')
            countity = float(request.data.get('countity'))
            buy_price = float(request.data.get('buy_price'))
            sell_price = float(request.data.get('sell_price'))
            date = request.data.get('date')
            notes = request.data.get('notes')

            if supplies:
                try:
                    supplies_instance = Supplies.objects.get(supply_name=supplies,user=user_instance)

                    reciept_instance = Reciept.objects.get(id=id, user=user_instance)
                    reciept_instance.delete()
                    reciept_instance.type = Type.objects.get(type=types, user=user_instance)
                    reciept_instance.supply = Supplies.objects.get(supply_name=supplies,user=user_instance)
                    reciept_instance.countity = countity
                    reciept_instance.buy_price = buy_price
                    reciept_instance.sell_price = sell_price
                    reciept_instance.total = calculateTotalPrice(countity,supplies_instance.unit,buy_price)
                    reciept_instance.date = date
                    reciept_instance.notes = notes
                    reciept_instance.save()
                    
                    return Response({'message': 'Reciept updated successfully!'}, status=status.HTTP_200_OK)
                except Reciept.DoesNotExist:
                    return Response({'error': 'Reciept not found'}, status=status.HTTP_404_NOT_FOUND)
            else:
                return Response({'error': 'Supplies not provided'}, status=status.HTTP_400_BAD_REQUEST)

        elif request.method == 'DELETE':
            reciept_to_delete = request.data.get('id')

            if reciept_to_delete:
                try:
                    reciept_instance = Reciept.objects.get(id=reciept_to_delete, user=user_instance)
                    reciept_instance.delete()
                    return Response({'message': 'Reciept deleted successfully!'}, status=status.HTTP_200_OK)
                except Reciept.DoesNotExist:
                    return Response({'error': 'Reciept not found'}, status=status.HTTP_404_NOT_FOUND)
            else:
                return Response({'error': 'Reciept ID not provided'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'error': 'Invalid request method'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"EditReciepts error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_Reciepts(request, username, query):
    try:
        user_instance = User.objects.get(user_name=username)
        
        # Find Supplies and Types matching the query
        supplies = Supplies.objects.filter(supply_name__icontains=query)
        types = Type.objects.filter(type__icontains=query)
        
        # Filter Reciept objects based on the found Supplies and Types
        reciepts = Reciept.objects.filter(
            Q(supply__in=supplies) | Q(type__in=types) | Q(date__icontains=query), user=user_instance
        )
        
        recieptSerializer = RecieptSerializer(reciepts, many=True)
        types_serializer = TypeSerializer(types, many=True)
        
        return Response({
            'reciepts': recieptSerializer.data,
            'types': types_serializer.data
        }, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Search Types error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ------------------------------------------------------------------------------------

# Manging Emploies EndPoints

@api_view(['POST','GET'])
@permission_classes([IsAuthenticated])
def employ_Employees (request,username):
    try:
        user = User.objects.get(user_name = username)

        if request.method == 'POST':
            user_data = request.data.get('user')
            emp_name = request.data.get('emp_name')
            salary = request.data.get('salary')
            emp_date = request.data.get('emp_date')
            if user_data:
                user_instance = User.objects.get(user_name = user_data)
                
                if emp_name:
                    Employee.objects.create(user=user_instance,employee_name=emp_name,date_of_employment=emp_date,salary=salary)
                        
                    return Response({'message': 'Employee Added successfully!'}, status=status.HTTP_200_OK)
                
        
        if request.method == 'GET':
            employees = Employee.objects.filter(user=user)
            serializer = EmployeeSerializer(employees, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
    except User.DoesNotExist:
        return Response({'error': 'User not found'})
    except Exception as e:
        return Response({'Employee error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def edit_employee(request, username):
    try:
        user_instance = User.objects.get(user_name=username)

        if request.method == 'PUT':
            name = request.data.get('emp_name')
            salary = request.data.get('salary')
            date = request.data.get('emp_date')
            edited_employee = request.data.get('new_emp')

            if name:
                try:
                    employee_instance = Employee.objects.get(user=user_instance,employee_name=name,)
                    employee_instance.delete()
                    employee_instance.employee_name = edited_employee
                    employee_instance.salary = salary
                    employee_instance.date_of_employment = date
                    employee_instance.save()
                    
                    return Response({'message': 'Employee updated successfully!'}, status=status.HTTP_200_OK)
                except Reciept.DoesNotExist:
                    return Response({'error': 'Employee not found'}, status=status.HTTP_404_NOT_FOUND)
            else:
                return Response({'error': 'Employee not provided'}, status=status.HTTP_400_BAD_REQUEST)

        if request.method == 'DELETE':
            employee_to_delete = request.data.get('employee')

            if employee_to_delete:
                try:
                    employee_instance = Employee.objects.get(employee_name=employee_to_delete, user=user_instance)
                    employee_instance.delete()
                    return Response({'message': 'Employee deleted successfully!'}, status=status.HTTP_200_OK)
                except Employee.DoesNotExist:
                    return Response({'error': 'Employee not found'}, status=status.HTTP_404_NOT_FOUND)
            else:
                return Response({'error': 'Employee Name not provided'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'error': 'Invalid request method'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
        
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Edit Employee error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_Employee(request, username, query):
    try:
        user_instance = User.objects.get(user_name=username)
        employees = Employee.objects.filter(Q(employee_name__icontains=query) | Q(date_of_employment__icontains=query), user=user_instance)
        serializer = EmployeeSerializer(employees, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Search Employee error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ------------------------------------------------------------------------------------

# Managing CustomerName Endpoints

@api_view(['POST','GET'])
@permission_classes([IsAuthenticated])
def manage_customers(request,username):
    try:
        user = User.objects.get(user_name = username)

        if request.method == 'POST':
            customer = request.data.get('customer')
            user_data = request.data.get('user')

            if customer and user_data:
                user_instance = User.objects.get(user_name = user_data)
                CustomerName.objects.create(customer_name=customer,user = user_instance)

            return Response({'message': 'Customer Added successfully!'}, status=status.HTTP_200_OK)

        if request.method == 'GET':
            customer = CustomerName.objects.filter(user=user)
            serializer = CustomerNameSerializer(customer, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
    except User.DoesNotExist:
        return Response({'error': 'User not found'})
    except Exception as e:
        logger.error(f"Customer error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def edit_customers(request, username):
    try:
        user_instance = User.objects.get(user_name=username)

        if request.method == 'PUT':
            old_customer = request.data.get('old_customer')
            new_customer = request.data.get('new_customer')

            if old_customer and new_customer:
                try:
                    customer_instance = CustomerName.objects.get(customer_name=old_customer, user=user_instance)
                    old_debt = customer_instance.total_debt
                    customer_instance.delete()
                    CustomerName.objects.create(user = user_instance,customer_name = new_customer,total_debt = old_debt)
                    return Response({'message': 'Customer updated successfully!'}, status=status.HTTP_200_OK)
                except CustomerName.DoesNotExist:
                    return Response({'error': 'Customer not found'}, status=status.HTTP_404_NOT_FOUND)

        elif request.method == 'DELETE':
            customer_to_delete = request.data.get('customer')

            if customer_to_delete:
                try:
                    customer_instance = CustomerName.objects.get(customer_name=customer_to_delete, user=user_instance)
                    customer_instance.delete()
                    return Response({'message': 'Customer deleted successfully!'}, status=status.HTTP_200_OK)
                except CustomerName.DoesNotExist:
                    return Response({'error': 'Customer not found'}, status=status.HTTP_404_NOT_FOUND)

    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Edit Customer error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_customers(request, username, customer):
    try:
        user_instance = User.objects.get(user_name=username)
        customer = CustomerName.objects.filter(Q(customer_name__icontains=customer), user=user_instance)
        serializer = CustomerNameSerializer(customer, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Search Customer error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ------------------------------------------------------------------------------------

# Managing MoneyIncome Endpoints

@api_view(['POST','GET'])
@permission_classes([IsAuthenticated])
def manage_Income (request,username):
    try:
        user = User.objects.get(user_name = username)

        if request.method == 'POST':
            user_data = request.data.get('user')
            money_from = request.data.get('money_from')
            total = float(request.data.get('total'))
            date = request.data.get('date')
            notes = request.data.get('notes')

            if user_data:
                user_instance = User.objects.get(user_name = user_data)
                customer_instance = CustomerName.objects.get(customer_name=money_from,user=user_instance)
                if money_from:
                    MoneyIncome.objects.create(user=user_instance,money_from=customer_instance,total=total,date=date,notes=notes)
                        
                    return Response({'message': 'Income Added successfully!'}, status=status.HTTP_200_OK)
                
        
        if request.method == 'GET':
            income = MoneyIncome.objects.filter(user=user)
            serializer = MoneyIncomeSerializer(income, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
    except User.DoesNotExist:
        return Response({'error': 'User not found'})
    except Exception as e:
        return Response({'Money Income error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def edit_Income(request, username):
    try:
        user_instance = User.objects.get(user_name=username)

        if request.method == 'PUT':
            id = request.data.get('id')
            money_from = request.data.get('money_from')
            total = float(request.data.get('total'))
            date = request.data.get('date')
            notes = request.data.get('notes')

            if id:
                try:
                    income_instace = MoneyIncome.objects.get(user=user_instance,id=id)
                    income_instace.delete()
                    customer_instance = CustomerName.objects.get(user=user_instance,customer_name=money_from)
                    income_instace.money_from = customer_instance
                    income_instace.total = total
                    income_instace.date = date
                    income_instace.notes = notes
                    income_instace.save()
                    
                    return Response({'message': 'Income updated successfully!'}, status=status.HTTP_200_OK)
                except Reciept.DoesNotExist:
                    return Response({'error': 'Income not found'}, status=status.HTTP_404_NOT_FOUND)
            else:
                return Response({'error': 'Income not provided'}, status=status.HTTP_400_BAD_REQUEST)

        if request.method == 'DELETE':
            income_to_delete = request.data.get('id')

            if income_to_delete:
                try:
                    income_instace = MoneyIncome.objects.get(id=income_to_delete, user=user_instance)
                    income_instace.delete()
                    return Response({'message': 'Income deleted successfully!'}, status=status.HTTP_200_OK)
                except Reciept.DoesNotExist:
                    return Response({'error': 'Income not found'}, status=status.HTTP_404_NOT_FOUND)
            else:
                return Response({'error': 'Income ID not provided'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'error': 'Invalid request method'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
        
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Edit Income error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_Income(request, username, query):
    try:
        user_instance = User.objects.get(user_name=username)
        customer = CustomerName.objects.filter(customer_name__icontains=query,user=user_instance)

        income = MoneyIncome.objects.filter(Q(money_from__in=customer), user=user_instance)
        serializer = MoneyIncomeSerializer(income, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Search Income error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ------------------------------------------------------------------------------------

# Manging Payment Endpoints

@api_view(['POST','GET'])
@permission_classes([IsAuthenticated])
def manage_payment (request,username):
    try:
        user = User.objects.get(user_name = username)

        if request.method == 'POST':
            user_data = request.data.get('user')
            money_for = request.data.get('money_for')
            total = float(request.data.get('total'))
            date = request.data.get('date')
            notes = request.data.get('notes')

            if user_data:
                user_instance = User.objects.get(user_name = user_data)
                
                if money_for:
                    Payment.objects.create(user=user_instance,money_for=money_for,total=total,date=date,notes=notes)
                        
                    return Response({'message': 'Payment Added successfully!'}, status=status.HTTP_200_OK)
                
        
        if request.method == 'GET':
            payment = Payment.objects.filter(user=user)
            serializer = PaymentSerializer(payment, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
    except User.DoesNotExist:
        return Response({'error': 'User not found'})
    except Exception as e:
        return Response({'Payment error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def edit_payment(request, username):
    try:
        user_instance = User.objects.get(user_name=username)

        if request.method == 'PUT':
            id = request.data.get('id')
            money_for = request.data.get('money_for')
            total = float(request.data.get('total'))
            date = request.data.get('date')
            notes = request.data.get('notes')

            if id:
                try:
                    payment_instance = Payment.objects.get(user=user_instance,id=id)
                    payment_instance.delete()
                    payment_instance.money_for = money_for
                    payment_instance.total = total
                    payment_instance.date = date
                    payment_instance.notes = notes
                    payment_instance.save()
                    
                    return Response({'message': 'Payment updated successfully!'}, status=status.HTTP_200_OK)
                except Reciept.DoesNotExist:
                    return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)
            else:
                return Response({'error': 'Payment not provided'}, status=status.HTTP_400_BAD_REQUEST)

        if request.method == 'DELETE':
            payment_to_delete = request.data.get('id')

            if payment_to_delete:
                try:
                    income_instace = Payment.objects.get(id=payment_to_delete, user=user_instance)
                    income_instace.delete()
                    return Response({'message': 'Payment deleted successfully!'}, status=status.HTTP_200_OK)
                except Reciept.DoesNotExist:
                    return Response({'error': 'Payment not found'}, status=status.HTTP_404_NOT_FOUND)
            else:
                return Response({'error': 'Payment ID not provided'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'error': 'Invalid request method'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
        
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Edit Payment error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_payment(request, username, query):
    try:
        user_instance = User.objects.get(user_name=username)
        payment = Payment.objects.filter(Q(money_for__icontains=query), user=user_instance)
        serializer = PaymentSerializer(payment, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Search Payment error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ------------------------------------------------------------------------------------

# Managing CustomerSell EndPoints

@api_view(['POST','GET'])
@permission_classes([IsAuthenticated])
def customer_Sell(request,username):
    try:
        user = User.objects.get(user_name = username)

        if request.method == 'POST':
            user_data = request.data.get('user')
            customer_name = request.data.get('customer_name')
            date_of_buying = request.data.get('date_of_buying')
            supply = request.data.get('supply')
            price = float(request.data.get('price'))
            countity = float(request.data.get('countity'))
            debt = float(request.data.get('debt'))
            paid = float(request.data.get('paid'))
            notes = request.data.get('notes')
            
            if user_data:
                user_instance = User.objects.get(user_name = user_data)
                customer_instance = CustomerName.objects.get(user=user_instance,customer_name = customer_name)
               

                if customer_instance:
                    try:
                        supplies_instance = Supplies.objects.get(supply_name = supply,user = user_instance)
                    except Supplies.DoesNotExist:
                        return Response({'Error':'Supply Does Not Exist'},status=status.HTTP_404_NOT_FOUND)
                        

                    Customer.objects.create(user=user_instance,customer_name=customer_instance,
                                            supply=supplies_instance,countity=countity,price=price,
                                            debt=debt,paid=paid,date_of_buying=date_of_buying,
                                            total = calculateTotalPrice(countity,supplies_instance.unit,price),
                                            notes=notes)
                        
                    return Response({'message': 'Customer Sold successful!'}, status=status.HTTP_200_OK)
                else:
                    return Response({'message': 'Customer Does Not Exists Please Insert And Existing Customer Name'},status=status.HTTP_404_NOT_FOUND)
                
        
        if request.method == 'GET':
            sells = Customer.objects.filter(user=user)
            serializer = CustomerSerializer(sells, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
    except User.DoesNotExist:
        logger.error(f"User {username} not found.")
        return Response({'Customer Sell error': 'User not found'})
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def edit_customerSell(request, username):
    try:
        user_instance = User.objects.get(user_name=username)

        if request.method == 'PUT':
            id = float(request.data.get('id'))
            customer_name = request.data.get('customer_name')
            date_of_buying = request.data.get('date_of_buying')
            supply = request.data.get('supply')
            price = float(request.data.get('price'))
            countity = float(request.data.get('countity'))
            debt = float(request.data.get('debt'))
            paid = float(request.data.get('paid'))
            notes = request.data.get('notes')

            if customer_name and supply:
                try:
                    supplies_instance = Supplies.objects.get(supply_name=supply,user=user_instance)

                    customerSell_instance = Customer.objects.get(id=id, user=user_instance)
                    customerSell_instance.delete()
                    customerSell_instance.customer_name = CustomerName.objects.get(customer_name=customer_name, user=user_instance)
                    customerSell_instance.supply = supplies_instance
                    customerSell_instance.countity = countity
                    customerSell_instance.price = price
                    customerSell_instance.debt = debt
                    customerSell_instance.paid = paid
                    customerSell_instance.date_of_buying = date_of_buying
                    customerSell_instance.total = calculateTotalPrice(countity,supplies_instance.unit,price)
                    customerSell_instance.notes = notes
                    customerSell_instance.save()
                    
                    return Response({'message': 'Customer Sell updated successfully!'}, status=status.HTTP_200_OK)
                except Reciept.DoesNotExist:
                    return Response({'error': 'Customer Sell not found'}, status=status.HTTP_404_NOT_FOUND)
            else:
                return Response({'error': 'Customer Name not provided'}, status=status.HTTP_400_BAD_REQUEST)

        elif request.method == 'DELETE':
            sell_to_delete = request.data.get('id')

            if sell_to_delete:
                try:
                    customerSell_instance = Customer.objects.get(id=sell_to_delete, user=user_instance)
                    customerSell_instance.delete()
                    return Response({'message': 'Customer Sell deleted successfully!'}, status=status.HTTP_200_OK)
                except Reciept.DoesNotExist:
                    return Response({'error': 'Customer Sell not found'}, status=status.HTTP_404_NOT_FOUND)
            else:
                return Response({'error': 'Customer ID not provided'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'error': 'Invalid request method'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Edit Customer Sell error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_CustomerSell(request, username, query):
    try:
        user_instance = User.objects.get(user_name=username)
        
        # Find Supplies and Types matching the query
        supplies = Supplies.objects.filter(supply_name__icontains=query)
        customer = CustomerName.objects.filter(customer_name__icontains=query)
        
        # Filter Reciept objects based on the found Supplies and Types
        customerSell = Customer.objects.filter(
            Q(supply__in=supplies) | Q(customer_name__in=customer) | Q(date_of_buying__icontains=query), user=user_instance
        )
        
        customerSell_serializer = CustomerSerializer(customerSell, many=True)
        
        return Response({
            'customerSell': customerSell_serializer.data,
        }, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Search Customer Sell error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ------------------------------------------------------------------------------------

# Managing Sells EndPoints

@api_view(['POST','GET'])
@permission_classes([IsAuthenticated])
def sells(request,username):
    try:
        user = User.objects.get(user_name = username)

        if request.method == 'POST':
            user_data = request.data.get('user')
            supplies = request.data.get('supplies')
            countity = float(request.data.get('countity'))
            price = float(request.data.get('price'))
            date = request.data.get('date')
            notes = request.data.get('notes')
            
            if user_data:
                user_instance = User.objects.get(user_name = user_data)
                supplies_instance = Supplies.objects.get(supply_name = supplies,user = user_instance)
                if supplies:
                    Sell.objects.create(user=user_instance,supply=supplies_instance,
                                            countity=countity,price=price,
                                            date=date,
                                            total = calculateTotalPrice(countity,supplies_instance.unit,price),
                                            notes=notes)
                    return Response({'message': 'Sold successfully!'}, status=status.HTTP_200_OK)
                else:
                    return Response({'message': 'Supply Does Not Exists Please Insert An Existing Supply'},status=status.HTTP_404_NOT_FOUND)
                
        
        if request.method == 'GET':
            sells = Sell.objects.filter(user=user)
            serializer = SellSerializer(sells, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
    except User.DoesNotExist:
        logger.error(f"User {username} not found.")
        return Response({'Sell error': 'User not found'})
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def edit_sells(request, username):
    try:
        user_instance = User.objects.get(user_name=username)

        if request.method == 'PUT':
            id = request.data.get('id')
            supplies = request.data.get('supply')
            countity = float(request.data.get('countity'))
            price = float(request.data.get('price'))
            date = request.data.get('date')
            notes = request.data.get('notes')

            print(id,supplies,countity,price,date,notes)

            if supplies:
                try:
                    supplies_instance = Supplies.objects.get(supply_name=supplies,user=user_instance)

                    sell_instance = Sell.objects.get(id=id, user=user_instance)
                    sell_instance.delete()
                    sell_instance.supply = supplies_instance
                    sell_instance.countity = countity
                    sell_instance.price = price
                    sell_instance.date = date
                    sell_instance.total = calculateTotalPrice(countity,supplies_instance.unit,price)
                    sell_instance.notes = notes
                    sell_instance.save()
                    
                    return Response({'message': 'Sell updated successfully!'}, status=status.HTTP_200_OK)
                except Sell.DoesNotExist:
                    return Response({'error': 'Supplies not found'}, status=status.HTTP_404_NOT_FOUND)
            else:
                return Response({'error': 'Supplies not provided'}, status=status.HTTP_400_BAD_REQUEST)

        elif request.method == 'DELETE':
            sell_to_delete = request.data.get('id')

            if sell_to_delete:
                try:
                    sell_instance = Sell.objects.get(id=sell_to_delete, user=user_instance)
                    sell_instance.delete()
                    return Response({'message': 'Sell deleted successfully!'}, status=status.HTTP_200_OK)
                except Sell.DoesNotExist:
                    return Response({'error': 'Sell not found'}, status=status.HTTP_404_NOT_FOUND)
            else:
                return Response({'error': 'Sell ID not provided'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'error': 'Invalid request method'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    except User.DoesNotExist:
        return Response({'Edit Sell error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Sell error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_sells(request, username, query):
    try:
        user_instance = User.objects.get(user_name=username)
        
        # Find Supplies and Types matching the query
        supplies = Supplies.objects.filter(supply_name__icontains=query)
        
        # Filter Reciept objects based on the found Supplies and Types
        sell = Sell.objects.filter(
            Q(supply__in=supplies) | Q(date__icontains=query), user=user_instance
        )
        
        sellSerializer = SellSerializer(sell, many=True)
       
        
        return Response({
            'sells': sellSerializer.data,
        }, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Search Sell error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ------------------------------------------------------------------------------------

# Managing MoneyFund EndPoints

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_fund(request, username):
    try:
        user_instance = User.objects.get(user_name=username)
        moneyfund_instance = MoneyFund.objects.get(user=user_instance)
        serializer = MoneyFundSerializer(moneyfund_instance)
        logger.debug(f"Serialized data: {serializer.data}")
        return Response(serializer.data, status=status.HTTP_200_OK)

    except User.DoesNotExist:
        logger.error(f"User {username} does not exist")  # Debugging
        return Response({'Money Fund Error': 'User Does Not Exist'}, status=status.HTTP_404_NOT_FOUND)

    except MoneyFund.DoesNotExist:
        logger.error(f"MoneyFund does not exist for user {username}")  # Debugging
        return Response({'Error': 'MoneyFund Does Not Exist for This User'}, status=status.HTTP_404_NOT_FOUND)
    
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def move_fund_fromSells_to_perma(request, username):
    try:
        sells_fund = float(request.data.get("sellsFund"))

        user_instance = User.objects.get(user_name=username)
        moneyfund_instance = MoneyFund.objects.get(user=user_instance)

        moneyfund_instance.permanant_fund += sells_fund
        moneyfund_instance.sells_fund = 0
        moneyfund_instance.save()
        

        return Response({"Message":"Sells Fund Moved To Permanant Fund Successflly"}, status=status.HTTP_200_OK)

    except User.DoesNotExist:
        logger.error(f"User {username} does not exist")  # Debugging
        return Response({'Money Fund Error': 'User Does Not Exist'}, status=status.HTTP_404_NOT_FOUND)

    except MoneyFund.DoesNotExist:
        logger.error(f"MoneyFund does not exist for user {username}")  # Debugging
        return Response({'Error': 'MoneyFund Does Not Exist for This User'}, status=status.HTTP_404_NOT_FOUND)

# ------------------------------------------------------------------------------------

# Managing DispatchSupplies Endpoints

@api_view(['POST','GET'])
@permission_classes([IsAuthenticated])
def dispatches(request,username):
    try:
        user = User.objects.get(user_name = username)

        if request.method == 'POST':
            user_data = request.data.get('user')
            supplies = request.data.get('supply')
            countity = float(request.data.get('countity'))
            price = float(request.data.get('buy_price'))
            date = request.data.get('dispatch_date')
            reason = request.data.get('reason')
            
            if user_data:
                user_instance = User.objects.get(user_name = user_data)
                supplies_instance = Supplies.objects.get(supply_name = supplies,user = user_instance)
                if supplies:
                    DispatchSupply.objects.create(user=user_instance,supply=supplies_instance,
                                                  countity=countity,buy_price=price,dispatch_date=date,
                                                  reason=reason)
                    return Response({'message': 'Supply Disptached successfully!'}, status=status.HTTP_200_OK)
                else:
                    return Response({'message': 'Supply Does Not Exists Please Insert An Existing Supply'},status=status.HTTP_404_NOT_FOUND)
                
        
        if request.method == 'GET':
            dispatch = DispatchSupply.objects.filter(user=user)
            serializer = DispatchSupplySerializer(dispatch, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
    except User.DoesNotExist:
        logger.error(f"User {username} not found.")
        return Response({'Disptach Supplies error': 'User not found'})
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['PUT', 'DELETE'])
@permission_classes([IsAuthenticated])
def edit_dispatches(request, username):
    try:
        user_instance = User.objects.get(user_name=username)

        if request.method == 'PUT':
            id = float(request.data.get('id'))
            supplies = request.data.get('supply')
            countity = float(request.data.get('countity'))
            price = float(request.data.get('buy_price'))
            date = request.data.get('dispatch_date')
            reason = request.data.get('reason')

            if supplies:
                try:
                    supplies_instance = Supplies.objects.get(supply_name=supplies,user=user_instance)

                    dispatch_instance = DispatchSupply.objects.get(id=id, user=user_instance)
                    dispatch_instance.delete()
                    dispatch_instance.supply = supplies_instance
                    dispatch_instance.countity = countity
                    dispatch_instance.buy_price = price
                    dispatch_instance.dispatch_date = date
                    dispatch_instance.reason = reason
                    dispatch_instance.save()
                    
                    return Response({'message': 'Disptach updated successfully!'}, status=status.HTTP_200_OK)
                except Sell.DoesNotExist:
                    return Response({'error': 'Dispatch not found'}, status=status.HTTP_404_NOT_FOUND)
            else:
                return Response({'error': 'Supplies not provided'}, status=status.HTTP_400_BAD_REQUEST)

        elif request.method == 'DELETE':
            dispatch_to_delete = request.data.get('id')

            if dispatch_to_delete:
                try:
                    dispatch_instance = DispatchSupply.objects.get(id=dispatch_to_delete, user=user_instance)
                    dispatch_instance.delete()
                    return Response({'message': 'Disptach deleted successfully!'}, status=status.HTTP_200_OK)
                except Sell.DoesNotExist:
                    return Response({'error': 'Dispatch not found'}, status=status.HTTP_404_NOT_FOUND)
            else:
                return Response({'error': 'Disptach ID not provided'}, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({'error': 'Invalid request method'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Edit Disptach error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_dispatches(request, username, query):
    try:
        user_instance = User.objects.get(user_name=username)
        
        # Find Supplies and Types matching the query
        supplies = Supplies.objects.filter(supply_name__icontains=query)
        
        # Filter Reciept objects based on the found Supplies and Types
        dispatches = DispatchSupply.objects.filter(
            Q(supply__in=supplies) | Q(dispatch_date__icontains=query), user=user_instance
        )
        
        dispatchserializer = DispatchSupplySerializer(dispatches, many=True)
       
        
        return Response({
            'dispatched': dispatchserializer.data,
        }, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Search Disptach error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# ------------------------------------------------------------------------------------

# Managing Inventory EndPoints

@api_view(['POST','GET'])
@permission_classes([IsAuthenticated])
def generate_inventory (request,username):
    try:
        user = User.objects.get(user_name = username)

        if request.method == 'POST':
           user_data = request.data.get('user')
           supply = request.data.get('supply')
           start_date = request.data.get('start_date')
           end_date = request.data.get('end_date')

           if user_data:
               user_instance = User.objects.get(user_name = user_data)
               supply_instance = Supplies.objects.get(user=user_instance,supply_name=supply)
               Inventory.objects.create(user=user_instance,supply=supply_instance,start_date=start_date,end_date=end_date)

               return Response({'Message':'Inventory Generated Successfully'},status=status.HTTP_200_OK)                
        
        if request.method == 'GET':
            inventory = Inventory.objects.filter(user=user)
            serializer = InventorySerializer(inventory, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        
    except User.DoesNotExist:
        logger.error(f"User {username} not found.")
        return Response({'Inventory error': 'User not found'})
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def delete_inventory (request,username):
    try:
        user_instance = User.objects.get(user_name = username)

        inventory_to_delete = request.data.get('id')

        if inventory_to_delete:
            try:
                inventory_instance = Inventory.objects.get(id=inventory_to_delete, user=user_instance)
                inventory_instance.delete()
                return Response({'message': 'Inventory deleted successfully!'}, status=status.HTTP_200_OK)
            except Inventory.DoesNotExist:
                return Response({'error': 'Inventory not found'}, status=status.HTTP_404_NOT_FOUND)
        else:
            return Response({'error': 'Inventory ID not provided'}, status=status.HTTP_400_BAD_REQUEST)
    except User.DoesNotExist:
        logger.error(f"User {username} not found.")
        return Response({'Edit inventory error': 'User not found'})
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def search_inventory(request, username, query):
    try:
        user_instance = User.objects.get(user_name=username)
        
        # Find Supplies and Types matching the query
        supplies = Supplies.objects.filter(supply_name__icontains=query)
        
        # Filter Reciept objects based on the found Supplies and Types
        inventory = Inventory.objects.filter(
            Q(supply__in=supplies) | Q(inventory_date__icontains=query) | Q(start_date__icontains=query)
            | Q(end_date__icontains=query), user=user_instance
        )
        
        inventorySerializer = InventorySerializer(inventory, many=True)
       
        return Response({
            'dispatched': inventorySerializer.data,
        }, status=status.HTTP_200_OK)
    except User.DoesNotExist:
        return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
    except Exception as e:
        logger.error(f"Search Inventory error: {e}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
#--------------------------------------------------------------------------
# AI Integration

class ImageAnalysisView(APIView):
    def post(self, request):
        try:
            serializer = ImageDataSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
            image_data = data['image'].split(",")[1]
            image_bytes = base64.b64decode(image_data)
            image = Image.open(BytesIO(image_bytes))
            responses = analyze_image(image, data['dict_of_vars'])
            return Response({
            "message": "Image processed",
            "data": responses,
            "status": "success"
            })
        
        except  Exception as e:
            return Response({'Error':str(e)},status=status.HTTP_400_BAD_REQUEST)

    
#--------------------------------------------------------------------------
# Expoting Data

# def export_all_data_excel(request, username):
#     user = User.objects.get(user_name=username)

#     # Get data from all models related to the user
#     user_data = pd.DataFrame(list(User.objects.filter(user_name=user.user_name).values()))
#     type_data = pd.DataFrame(list(Type.objects.filter(user=user).values()))
#     supplies_data = pd.DataFrame(list(Supplies.objects.filter(user=user).values()))
#     Dispatch_data = pd.DataFrame(list(DispatchSupply.objects.filter(user=user).values()))
#     customer_name_data = pd.DataFrame(list(CustomerName.objects.filter(user=user).values()))
#     customer_data = pd.DataFrame(list(Customer.objects.filter(user=user).values()))
#     employee_data = pd.DataFrame(list(Employee.objects.filter(user=user).values()))
#     money_fund_data = pd.DataFrame(list(MoneyFund.objects.filter(user=user).values()))
#     sell_data = pd.DataFrame(list(Sell.objects.filter(user=user).values()))
#     reciept_data = pd.DataFrame(list(Reciept.objects.filter(user=user).values()))
#     money_income_data = pd.DataFrame(list(MoneyIncome.objects.filter(user=user).values()))
#     payment_data = pd.DataFrame(list(Payment.objects.filter(user=user).values()))
#     inventory_data = pd.DataFrame(list(Inventory.objects.filter(user=user).values()))

#     # Create a Pandas Excel writer using openpyxl as the engine.
#     with pd.ExcelWriter('all_data_data.xlsx', engine='openpyxl') as writer:
#         # Write each DataFrame to a specific sheet
#         user_data.to_excel(writer, sheet_name='User', index=False)
#         type_data.to_excel(writer, sheet_name='Type', index=False)
#         supplies_data.to_excel(writer, sheet_name='Supplies', index=False)
#         Dispatch_data.to_excel(writer, sheet_name='DispatchSupply', index=False)
#         customer_name_data.to_excel(writer, sheet_name='CustomerName', index=False)
#         customer_data.to_excel(writer, sheet_name='Customer', index=False)
#         employee_data.to_excel(writer, sheet_name='Employee', index=False)
#         money_fund_data.to_excel(writer, sheet_name='MoneyFund', index=False)
#         sell_data.to_excel(writer, sheet_name='Sell', index=False)
#         reciept_data.to_excel(writer, sheet_name='Reciept', index=False)
#         money_income_data.to_excel(writer, sheet_name='MoneyIncome', index=False)
#         payment_data.to_excel(writer, sheet_name='Payment', index=False)
#         inventory_data.to_excel(writer, sheet_name='Inventory', index=False)

#         workbook = writer.book
#         for sheet_name in writer.sheets:
#             worksheet = workbook[sheet_name]
#             for col in worksheet.columns:
#                 max_length = 0
#                 column = col[0].column_letter  # Get the column name
#                 for cell in col:
#                     if cell.value:
#                         max_length = max(max_length, len(str(cell.value)))
#                 adjusted_width = (max_length + 2)
#                 worksheet.column_dimensions[column].width = adjusted_width

#     # Open the file in binary mode to read
#     with open('all_data.xlsx', 'rb') as excel_file:
#         response = HttpResponse(excel_file.read(), content_type='application/vnd.ms-excel')
#         response['Content-Disposition'] = f'attachment; filename="{username}_all_data.xlsx"'
        
#     return response


def make_timezone_unaware(df):
    for col in df.columns:
        if df[col].dtype == 'datetime64[ns, UTC]':
            df[col] = df[col].dt.tz_localize(None)
    return df

def export_all_data_excel(request, username):
    user = User.objects.get(user_name=username)

    # Helper function to safely drop 'user_id' if it exists
    def prepare_data(queryset):
        df = pd.DataFrame(list(queryset))
        if not df.empty and 'user_id' in df.columns:
            df = df.drop(columns=['user_id'])
        return df

    # Get data from all models (automatically drops 'user_id' if present)
    type_data = prepare_data(Type.objects.filter(user=user).values())
    supplies_data = prepare_data(Supplies.objects.filter(user=user).values())
    Dispatch_data = prepare_data(DispatchSupply.objects.filter(user=user).values())
    customer_name_data = prepare_data(CustomerName.objects.filter(user=user).values())
    customer_data = prepare_data(Customer.objects.filter(user=user).values())
    employee_data = prepare_data(Employee.objects.filter(user=user).values())
    money_fund_data = prepare_data(MoneyFund.objects.filter(user=user).values())
    sell_data = prepare_data(Sell.objects.filter(user=user).values())
    reciept_data = prepare_data(Reciept.objects.filter(user=user).values())
    money_income_data = prepare_data(MoneyIncome.objects.filter(user=user).values())
    payment_data = prepare_data(Payment.objects.filter(user=user).values())
    inventory_data = prepare_data(Inventory.objects.filter(user=user).values())

    # Ensure all datetime columns are timezone-unaware
    data_frames = [type_data, supplies_data, Dispatch_data, customer_name_data, customer_data, 
                   employee_data, money_fund_data, sell_data, reciept_data, money_income_data, 
                   payment_data, inventory_data]
    data_frames = [make_timezone_unaware(df) for df in data_frames]

    # Create Excel file and adjust column widths (rest of your existing code)
    with pd.ExcelWriter('all_data.xlsx', engine='openpyxl') as writer:
        data_frames[0].to_excel(writer, sheet_name='Type', index=False)
        data_frames[1].to_excel(writer, sheet_name='Supplies', index=False)
        data_frames[2].to_excel(writer, sheet_name='DispatchSupply', index=False)
        data_frames[3].to_excel(writer, sheet_name='CustomerName', index=False)
        data_frames[4].to_excel(writer, sheet_name='Customer', index=False)
        data_frames[5].to_excel(writer, sheet_name='Employee', index=False)
        data_frames[6].to_excel(writer, sheet_name='MoneyFund', index=False)
        data_frames[7].to_excel(writer, sheet_name='Sell', index=False)
        data_frames[8].to_excel(writer, sheet_name='Reciept', index=False)
        data_frames[9].to_excel(writer, sheet_name='MoneyIncome', index=False)
        data_frames[10].to_excel(writer, sheet_name='Payment', index=False)
        data_frames[11].to_excel(writer, sheet_name='Inventory', index=False)

        # Auto-adjust column widths
        workbook = writer.book
        for sheet_name in writer.sheets:
            worksheet = workbook[sheet_name]
            for col in worksheet.columns:
                max_length = 0
                column = col[0].column_letter
                for cell in col:
                    if cell.value:
                        max_length = max(max_length, len(str(cell.value)))
                adjusted_width = (max_length + 2)
                worksheet.column_dimensions[column].width = adjusted_width

    # Return the Excel file as a response
    with open('all_data.xlsx', 'rb') as excel_file:
        response = HttpResponse(excel_file.read(), content_type='application/vnd.ms-excel')
        response['Content-Disposition'] = f'attachment; filename="{username}_all_data.xlsx"'
        
    return response

def make_timezone_aware(df):
    date_format='%m/%d/%Y'
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            # Convert naive datetime to UTC-aware
            if df[col].dt.tz is None:
                df[col] = df[col].dt.tz_localize('UTC')

    return df

def check_duplicate(model_class, user, data):
    # Define unique constraints for each model
    unique_fields_map = {
        'Type': ['type'],
        'Supplies': ['supply_name'],
        'CustomerName': ['customer_name'],
        'Employee': ['employee_name'],
    }
    
    unique_fields = unique_fields_map.get(model_class.__name__)
    if not unique_fields:
        return False
    
    filters = {field: data[field] for field in unique_fields}
    filters['user'] = user
    return model_class.objects.filter(**filters).exists()

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def import_Data(request, username):
    try:
        user = User.objects.get(user_name=username)
    except User.DoesNotExist:
        return JsonResponse({'error': 'User not found'}, status=400)
    
    if 'file' not in request.FILES:
        return JsonResponse({'error': 'No file uploaded'}, status=400)
    
    try:
        excel_file = request.FILES['file']
        model_map = {
            'Type': Type,
            'Supplies': Supplies,
            'DispatchSupply': DispatchSupply,
            'CustomerName': CustomerName,
            'Customer': Customer,
            'Employee': Employee,
            'MoneyFund': MoneyFund,
            'Sell': Sell,
            'Reciept': Reciept,
            'MoneyIncome': MoneyIncome,
            'Payment': Payment,
            'Inventory': Inventory,
        }
        sheet_order = [
            'Type', 'Supplies', 'DispatchSupply', 'CustomerName', 'Customer',
            'Employee', 'MoneyFund', 'Sell', 'Reciept', 'MoneyIncome',
            'Payment', 'Inventory'
        ]
        
        with transaction.atomic():
            xls = pd.ExcelFile(excel_file)
            processed_sheets = set()
            
            for sheet_name in sheet_order:
                if sheet_name == 'MoneyFund':
                    continue
                if sheet_name not in xls.sheet_names:
                    continue
                if sheet_name in processed_sheets:
                    continue
                processed_sheets.add(sheet_name)
                
                model_class = model_map.get(sheet_name)
                if not model_class:
                    continue
                
                df = pd.read_excel(xls, sheet_name=sheet_name)
                if 'id' in df.columns:
                    df = df.drop(columns=['id'])
                
                df = make_timezone_aware(df)
                df = df.where(pd.notnull(df), None)
                
                if sheet_name == "DispatchSupply":
                    continue

                for _, row in df.iterrows():
                    data = row.to_dict()

                    if check_duplicate(model_class, user, data):
                        continue

                    instance = model_class(user=user, **data)
                    instance.save()
        
    except Exception as e:
        return JsonResponse({'error': f'Error importing data: {str(e)}'}, status=400)
    
    return JsonResponse({'message': 'Data imported successfully'})





def export_all_data_pdf(request, username):
    user = User.objects.get(user_name=username)

    # Create the HttpResponse object with the appropriate PDF headers.
    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{username}_all_data.pdf"'

    # Create the PDF object, using the response object as its "file."
    doc = SimpleDocTemplate(response, pagesize=letter)
    elements = []

    # Title
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    heading_style = ParagraphStyle(
        name='Heading2Center', 
        parent=styles['Heading2'], 
        alignment=1  # Center alignment
    )
    body_style = styles['BodyText']

    title = f"Data Export for {user.user_name}"
    elements.append(Paragraph(title, title_style))

    # Fetch data from each model
    models_data = [
        ("Type", Type.objects.filter(user=user).values()),
        ("Supplies", Supplies.objects.filter(user=user).values()),
        ("DispactchSupply", DispatchSupply.objects.filter(user=user).values()),
        ("CustomerName", CustomerName.objects.filter(user=user).values()),
        ("Customer", Customer.objects.filter(user=user).values()),
        ("Employee", Employee.objects.filter(user=user).values()),
        ("MoneyFund", MoneyFund.objects.filter(user=user).values()),
        ("Sell", Sell.objects.filter(user=user).values()),
        ("Reciept", Reciept.objects.filter(user=user).values()),
        ("MoneyIncome", MoneyIncome.objects.filter(user=user).values()),
        ("Payment", Payment.objects.filter(user=user).values()),
        ("Inventory", Inventory.objects.filter(user=user).values())
    ]

    for model_name, data in models_data:
        elements.append(Paragraph(model_name, heading_style))
        if data.exists():
            for item in data:
                for key, value in item.items():
                    elements.append(Paragraph(f"{key}: {value}", body_style))
                elements.append(Paragraph("", body_style))  # Add a blank line between records
        else:
            elements.append(Paragraph("No data available.", body_style))
        elements.append(PageBreak())  # Add a page break after each model's data

    # Build the PDF
    doc.build(elements)

    return response




