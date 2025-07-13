import random
from collections import defaultdict
from .models import Timetable, Class, TimetableStatus, Course
from .validators import validate_timetable_constraints
from django.core.exceptions import ValidationError
from django.db.models import Q

# Define course slot requirements
#COURSE_SLOT_REQUIREMENTS = {'DL': 6, 'FS': 6, 'SE': 6, 'CE': 4}
COURSE_SLOT_REQUIREMENTS = {}
# Time slots and days
TIME_SLOTS = [1, 2, 3, 4, 5, 6, 7, 8]
DAYS = [1, 2, 3, 4, 5, 6]

# Precompute all data needed for the algorithm
def precompute_data(current_year, current_semester, section, dept):
    global valid_assignments, all_classes, course_class_map

    # Fetch all Class instances and store in a dictionary
    all_classes = {
        cls.main_id: cls
        for cls in Class.objects.select_related('course').filter(
            academic_year=current_year,
            semester=current_semester,
            section_id=section,
            dept=dept
        )
    }

    # Map courses to their corresponding class main_id values
    course_class_map = defaultdict(list)

    for cls in all_classes.values():
        if cls.course and cls.course.name:
            course_class_map[cls.course.name].append(cls.main_id)

    # Pre-validate all possible assignments
    print("Pre-computing constraint validation matrix...")
    ##print("DAYS:", DAYS, "Type of first element:", type(DAYS[0]))
    for main_id, cls in all_classes.items():
        for day in DAYS:
            #print(f"Processing day: {day}, Type: {type(day)}")
            for slot in TIME_SLOTS:
                try:
                    validate_timetable_constraints(main_id, day, slot, current_year, current_semester, section, dept)
                    valid_assignments[(main_id, day, slot)] = True
                except ValidationError:
                    valid_assignments[(main_id, day, slot)] = False
    print("Pre-computation completed.")

# Optimized fitness function using precomputed constraints
def fitness(individual):
    score = 0
    course_distribution = defaultdict(int)  # Tracks total slots per course
    clashes = defaultdict(set)  # Tracks faculty clashes per (day, slot)
    venue_clashes = defaultdict(set)  # Tracks venue clashes per (day, slot)
    course_per_day = defaultdict(lambda: defaultdict(int))  # Tracks course slots per day
    consecutive_main_courses = defaultdict(list)  # Tracks consecutive main course slots
    faculty_continuous = defaultdict(list)  # Tracks faculty continuous main course slots
    main_courses = {cls.course.name for cls in all_classes.values() if cls.course.course_type == 'none'}

    for day, slot, main_id, course_name in individual:
        # Check if assignment is valid (based on precomputed constraints)
        if not valid_assignments.get((main_id, day, slot), False):
            score -= 50  # Increased penalty for any validator constraint violation
            continue

        cls = all_classes[main_id]
        course_distribution[course_name] += 1  # Count slots per course
        course_per_day[day][course_name] += 1  # Count course slots per day
        score += 5  # Reward for valid assignment

        # Constraint 1: Slot Uniqueness (handled by validator, covered by valid_assignments)

        # Constraint 2: Venue Clashes
        venue_clashes[(day, slot)].add(cls.venue)
        if len(venue_clashes[(day, slot)]) > 1:
            score -= 50  # Penalty for venue clash

        # Constraint 3: Faculty Clashes
        for faculty in cls.faculty.all():  # Check all faculty
            if faculty.faculty_name != "Some faculty (-)":
                clashes[(day, slot)].add(faculty)
                if len(clashes[(day, slot)]) > 1:
                    score -= 50  # Penalty for faculty clash

        # Constraint 5: Faculty Continuous Main Courses
        for faculty in cls.faculty.all():  # Check all faculty
            if faculty.faculty_name != "Some faculty (-)" and course_name in main_courses:
                faculty_continuous[(day, faculty)].append((slot, course_name))

        # Constraint 4: Continuous Assignment Prevention (Main Courses)
        if course_name in main_courses:
            consecutive_main_courses[(day, course_name)].append(slot)
        
        # Constraint 5: Faculty Continuous Main Courses
        if faculty != "Some faculty (-)" and course_name in main_courses:
            faculty_continuous[(day, faculty)].append((slot, course_name))

    # Constraint 6: Max 2 Slots for Main Courses per Day
    for day, courses in course_per_day.items():
        for course, count in courses.items():
            if course in main_courses and count > 2:
                score -= 50 * (count - 2)  # Penalty for each extra slot

    # Constraint 3: Consecutive Main Courses
    for (day, course), slots in consecutive_main_courses.items():
        slots.sort()
        for i in range(len(slots) - 1):
            if slots[i + 1] == slots[i] + 1:
                score -= 50  # Penalty for consecutive main course slots

    # Constraint 5: Faculty Continuous Main Courses (Max 2)
    for (day, faculty), slot_courses in faculty_continuous.items():
        slots = sorted([slot for slot, course in slot_courses if course in main_courses])
        for i in range(len(slots) - 2):
            if slots[i + 2] <= slots[i] + 2:
                score -= 50  # Penalty for 3+ continuous main courses

    # Penalty for Unmet Slot Requirements
    for course, required_slots in COURSE_SLOT_REQUIREMENTS.items():
        diff = abs(course_distribution[course] - required_slots)
        score -= diff * 50  # Penalty for slot deviation

    return score

# Population generation using precomputed constraints
def generate_population(current_year, current_semester, section, dept, size=20):
    population = []
    for _ in range(size):
        individual = list((day, slot, main_id, course_name) for (day, slot), (main_id, course_name) in locked_assignments.items())

        course_slots_remaining = COURSE_SLOT_REQUIREMENTS.copy()
        for _, _, _, course in individual:
            if course in course_slots_remaining:
                course_slots_remaining[course] -= 1

        available_slots = [(day, slot) for day in DAYS for slot in TIME_SLOTS if (day, slot) not in locked_slots]
        main_courses = {cls.course.name for cls in all_classes.values() if cls.course.course_type == 'none'}

        # Keep trying until all slots are assigned or no more assignments are possible
        while available_slots and any(count > 0 for count in course_slots_remaining.values()):
            random.shuffle(available_slots)
            assigned_in_iteration = False

            for day, slot in available_slots[:]:  # Copy to allow removal
                # Check courses remaining to assign
                available_courses = [c for c, count in course_slots_remaining.items() if count > 0]
                if not available_courses:
                    break

                # Avoid assigning main courses more than twice per day
                assigned_courses_on_day = defaultdict(int)
                for d, _, _, c in individual:
                    if d == day:
                        assigned_courses_on_day[c] += 1
                available_courses = [c for c in available_courses if c not in main_courses or assigned_courses_on_day[c] < 2]

                if not available_courses:
                    available_slots.remove((day, slot))
                    continue

                course_name = random.choice(available_courses)
                valid_classes = [main_id for main_id in course_class_map[course_name]
                                if valid_assignments.get((main_id, day, slot), False)]

                if valid_classes:
                    random.shuffle(valid_classes)
                    assigned = False
                    for main_id in valid_classes:
                        try:
                            faculty = all_classes[main_id].faculty
                            validate_timetable_constraints(main_id, day, slot, current_year, current_semester, section, dept)
                            individual.append((day, slot, main_id, course_name))
                            course_slots_remaining[course_name] -= 1
                            assigned = True
                            assigned_in_iteration = True
                            available_slots.remove((day, slot))
                            break
                        except ValidationError:
                            continue
                    if not assigned:
                        print(f"Warning: No valid assignment for {course_name} on day {day}, slot {slot}")
                        available_slots.remove((day, slot))
                else:
                    available_slots.remove((day, slot))

            # If no assignments were made in this iteration, break to avoid infinite loop
            if not assigned_in_iteration:
                break

        population.append(individual)
    return population

# Two-point crossover
def crossover(parent1, parent2):
    locked_set = set(locked_assignments.keys())
    child = []

    # Build a dictionary for quick lookup
    parent2_dict = {(day, slot): (main_id, course_name) for day, slot, main_id, course_name in parent2}

    for day, slot, main_id, course_name in parent1:
        if (day, slot) in locked_set:
            child.append((day, slot, main_id, course_name))
        else:
            if (day, slot) in parent2_dict:
                child.append((day, slot, *parent2_dict[(day, slot)]))
            else:
                child.append((day, slot, main_id, course_name))

    return child

# Mutation using precomputed constraints
def mutate(individual, generation, max_generations):
    if not individual:
        return individual

    mutation_rate = max(0.5 - (0.4 * generation / max_generations), 0.1)
    course_slots = {course: sum(1 for _, _, _, c in individual if c == course) for course in COURSE_SLOT_REQUIREMENTS}

    # First, try to fill missing slots for courses below their requirement
    available_slots = [(day, slot) for day in DAYS for slot in TIME_SLOTS if (day, slot) not in [(d, s) for d, s, _, _ in individual]]
    random.shuffle(available_slots)

    for day, slot in available_slots:
        under_assigned_courses = [c for c, count in course_slots.items() if count < COURSE_SLOT_REQUIREMENTS[c]]
        if not under_assigned_courses:
            break
        course_name = random.choice(under_assigned_courses)
        valid_classes = [main_id for main_id in course_class_map[course_name]
                         if valid_assignments.get((main_id, day, slot), False)]
        if valid_classes:
            main_id = random.choice(valid_classes)
            individual.append((day, slot, main_id, course_name))
            course_slots[course_name] += 1

    # Then, perform random mutations on existing assignments
    for i in range(len(individual)):
        day, slot, _, old_course = individual[i]
        if (day, slot) in locked_slots:
            continue
        if random.random() < mutation_rate:
            available_courses = [c for c, count in course_slots.items()
                                 if count < COURSE_SLOT_REQUIREMENTS[c] and c != old_course]
            if available_courses:
                new_course = random.choice(available_courses)
                valid_classes = [main_id for main_id in course_class_map[new_course]
                                 if valid_assignments.get((main_id, day, slot), False)]
                if valid_classes:
                    main_id = random.choice(valid_classes)
                    individual[i] = (day, slot, main_id, new_course)
                    course_slots[old_course] -= 1
                    course_slots[new_course] += 1

    return individual

# Evaluate population using multiprocessing
def evaluate_population(population):
    return [fitness(ind) for ind in population]
    
# Dictionary to hold pre-assigned (locked) timetable slots
locked_slots = set()  # Format: (day, slot)
locked_assignments = {}  # Format: (day, slot): (main_id, course_name)

def load_locked_slots(current_year, current_semester, section, dept):
    global locked_slots, locked_assignments
    locked_slots.clear()
    locked_assignments.clear()

    qs = Timetable.objects.select_related('main_id__course').filter(main_id__academic_year=current_year, main_id__semester=current_semester, main_id__section_id=section, main_id__dept=dept).values_list('day', 'slot', 'main_id__main_id', 'main_id__course__name')

    for day, slot, main_id, course_name in qs:
        #print(f"Locked slot - Day: {day}, Type: {type(day)}, Slot: {slot}, Main ID: {main_id}, Course: {course_name}")
        key = (day, slot)
        locked_slots.add(key)
        locked_assignments[key] = (main_id, course_name)


# Run GA with precomputed validation checks
def run_ga_logic(current_year, current_semester, section, dept, count=0):
    print("Running Optimized Genetic Algorithm...")
    
    classes = Class.objects.filter(academic_year=current_year, semester=current_semester, section_id=section, dept=dept)
    relevant_courses = set(cls.course for cls in classes)    
    for course in relevant_courses:
        if course.course_type == 'none':
            COURSE_SLOT_REQUIREMENTS[course.name] = course.hours_per_week

    # Pre-calculated cache of valid assignments
    global valid_assignments, all_classes, course_class_map
    valid_assignments = {}
    all_classes = {}
    course_class_map = defaultdict(list)
    load_locked_slots(current_year, current_semester, section, dept)
    precompute_data(current_year, current_semester, section, dept)

    population = generate_population(current_year ,current_semester, section, dept, size=50)
    generations = 100
    best_fitness = -float('inf')
    stagnation_count = 0
    best_solution = None

    for gen in range(generations):
        fitness_scores = evaluate_population(population)
        sorted_pop = [(score, individual) for score, individual in zip(fitness_scores, population)]
        sorted_pop.sort(reverse=True)

        current_best_fitness = sorted_pop[0][0]
        if current_best_fitness > best_fitness:
            best_fitness = current_best_fitness
            best_solution = sorted_pop[0][1]
            stagnation_count = 0
            print(f"Generation {gen}: New best fitness: {best_fitness}")
        else:
            stagnation_count += 1

        if stagnation_count >= 20:
            print(f"Early stopping at generation {gen} - No improvement for {stagnation_count} generations")
            break

        population_size = max(15, len(population)//2) if stagnation_count > 5 else 30

        population = [individual for _, individual in sorted_pop]
        elite_count = max(3, population_size // 10)
        parents = population[:population_size // 2]
        next_generation = population[:elite_count]

        for _ in range(population_size - elite_count):
            parent1, parent2 = random.sample(parents, 2)
            child = crossover(parent1, parent2)
            child = mutate(child, gen, generations)
            next_generation.append(child)

        population = next_generation

    if best_solution is None:
        best_solution = max(population, key=fitness)

    print(f"Best fitness achieved: {best_fitness}")

    valid_solution = True
    constraint_violations = 0
    for day, slot, main_id, course_name in best_solution:
        if (day, slot) in locked_slots:
            continue
        if not valid_assignments.get((main_id, day, slot), False):
            constraint_violations += 1
            valid_solution = False
            print(f"Invalid assignment in best solution: main_id={main_id}, day={day}, slot={slot}")

    # Check COURSE_SLOT_REQUIREMENTS
    scheduled_slots = defaultdict(int)
    for day, slot, main_id, course_name in best_solution:
        if valid_assignments.get((main_id, day, slot), False):
            scheduled_slots[course_name] += 1

    requirements_met = all(scheduled_slots[course] == required
                           for course, required in COURSE_SLOT_REQUIREMENTS.items())

    # Retry if solution is invalid or requirements not met
    if (not valid_solution or not requirements_met) and count < 20:
        print(f"Retry {count + 1}: {constraint_violations} constraint violations, Requirements Met={requirements_met}")
        return run_ga_logic(current_year, current_semester, section, dept, count + 1)

    # Build a Q object to match all locked (day, slot) pairs
    locked_conditions = Q()
    for day, slot in locked_slots:
        locked_conditions |= Q(day=day, slot=slot)

    # Delete only entries that are NOT in locked slots
    if locked_conditions:
        Timetable.objects.filter(main_id__academic_year=current_year, main_id__semester=current_semester, main_id__section_id=section, main_id__dept=dept).exclude(locked_conditions).delete()
    else:
        Timetable.objects.filter(main_id__academic_year=current_year, main_id__semester=current_semester, main_id__section_id=section, main_id__dept=dept).delete()

    successful_assignments = 0
    #print("Best solution:", best_solution)
    for day, slot, main_id, course_name in best_solution:
        #print(f"Day: {day}, Type: {type(day)}, Slot: {slot}, Main ID: {main_id}, Course: {course_name}")
        if (day, slot) in locked_slots:
            continue
        if valid_assignments.get((main_id, day, slot), False):
            try:
                Timetable.objects.create(
                    main_id=all_classes[main_id],
                    day=day,
                    slot=slot
                )
                successful_assignments += 1
            except Exception as e:
                print(f"Error creating timetable entry: {e}")

    print(f"Created {successful_assignments} timetable entries")

    timetable_status, _ = TimetableStatus.objects.get_or_create(
        academic_year=current_year,
        semester=current_semester,
        section=section,
        dept=dept,
        defaults={'id': 1}
    )
    if requirements_met:
        timetable_status.status = 'completed' 
        timetable_status.save()
        print("Optimized Genetic Algorithm completed successfully.")
        
    else:
        print("Optimized Genetic Algorithm completed with partial solution.")